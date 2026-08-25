#!/system/bin/sh

SCRIPT_NAME="$(basename "$0")"

LOGMSG() {
    echo "I:$@" >> /tmp/recovery.log
}

LOGMSG "---$SCRIPT_NAME start---"

LOGMSG "Resetting SPL date to prevent anti-rollback protection..."
resetprop ro.build.version.security_patch 2023-12-31

# ============================================================================
# PHASE 1: Symlink fixes for liblp by-name resolution
# ============================================================================
LOGMSG "VABC DFE Fix: Fixing liblp by-name resolution bug via direct symlinks..."

# Symlink all raw block devices directly to /dev/block/by-name/ so liblp can find them!
for dev in /dev/block/sd* /dev/block/mmcblk* /dev/block/loop* /dev/block/dm-*; do
    if [ -b "$dev" ]; then
        base=$(basename "$dev")
        ln -sf "$dev" "/dev/block/by-name/$base"
    fi
done

LOGMSG "Initial symlinks created."

# update_engine_sideload creates dm-snapshot devices mid-flight.
# We run a background daemon to continuously symlink new dm-* devices to by-name.
(
    while true; do
        for dev in /dev/block/dm-*; do
            if [ -b "$dev" ]; then
                base=$(basename "$dev")
                if [ ! -L "/dev/block/by-name/$base" ]; then
                    ln -sf "$dev" "/dev/block/by-name/$base" 2>/dev/null
                fi
            fi
        done
        sleep 0.5
    done
) &
echo $! > /tmp/fox_symlink_daemon.pid

LOGMSG "Background daemon started to link newly created dm-* devices."

# ============================================================================
# PHASE 2: Backup recovery before ROM overwrites it
# ============================================================================
LOGMSG "Detecting active boot slot..."
slot="$(getprop ro.boot.slot_suffix)"
LOGMSG "Active boot slot: $slot"

LOGMSG "Backing up recovery.img before ROM overwrites..."
dd if="/dev/block/bootdevice/by-name/recovery${slot}" of="/tmp/fox_backup.img" bs=1M
sync

# ============================================================================
# PHASE 3: Unmount dynamic partitions to prevent update_engine Error 1
# ============================================================================
LOGMSG "Cleaning up dynamic partition mounts to prevent update_engine Error 1..."

# Kill FBE daemons that keep /vendor busy
for svc in qseecomd ssgtzd vendor.health-default vendor.weaver-nxp vendor.gatekeeper-1-0 vendor.secure_element_hal_service vendor.keymint-default; do
    stop $svc
done

# Kill any lingering processes using dynamic partitions
for pid in $(lsof | grep -E '/vendor|/system_root|/system_ext|/product|/odm' | awk '{print $2}' | sort -u); do
    kill -9 $pid 2>/dev/null
done

# Force recursively unmount dynamic partitions
for part in /vendor /system_root /system_ext /product /odm; do
    umount -R $part 2>/dev/null
    umount -l $part 2>/dev/null
done

LOGMSG "Dynamic partitions forcefully unmounted."

# ============================================================================
# PHASE 4: Wipe stale Virtual A/B state on /metadata
# ============================================================================
LOGMSG "Wiping Virtual A/B state to ensure clean OTA flash..."

# Force unmount any existing tmpfs or ext4 metadata to ensure we mount the real one
umount /metadata 2>/dev/null

# Mount /metadata as writable
mount -t f2fs /dev/block/bootdevice/by-name/metadata /metadata 2>/dev/null || mount -t ext4 /dev/block/bootdevice/by-name/metadata /metadata 2>/dev/null
mount -o remount,rw /metadata 2>/dev/null

# Clean ALL stale OTA state and massive log files that fill up /metadata
rm -rf /metadata/ota/*
rm -rf /metadata/gsi/ota/*
rm -f /metadata/boot_logcat.txt

# Create ALL directories required by update_engine_sideload:
# - /metadata/ota/snapshots: for per-partition snapshot state files
# - /metadata/gsi/ota: for COW image metadata tmpfiles (liblp WriteToImageFile)
mkdir -p /metadata/ota/snapshots
mkdir -p /metadata/gsi/ota
chmod -R 0750 /metadata/ota
chmod -R 0750 /metadata/gsi/ota

# Sync to disk so update_engine's internal remount sees these directories
sync

# UNMOUNT /metadata here!
# We MUST unmount it so update_engine_sideload can mount it natively using fs_mgr.
# This prevents update_engine from thinking it's unmounted due to namespace/symlink issues.
umount /metadata 2>/dev/null
LOGMSG "Virtual A/B state wiped. /metadata unmounted for update_engine."

# ============================================================================
# PHASE 5: Ensure /data/gsi/ota/ exists for COW image overflow (Error 7 fix)
# ============================================================================
# When super partition is full (~5.2GB), update_engine overflows COW images
# (vendor_a-cow-img.img, vendor_dlkm_a-cow-img.img) to /data/gsi/ota/.
# On DFE users, /data may not be mounted or the directory may not exist,
# causing fiemap_writer.cpp to fail with "No such file or directory" → Error 7.
LOGMSG "Ensuring /data is mounted for COW image overflow..."

DATA_MOUNTED=false
if mountpoint -q /data 2>/dev/null; then
    DATA_MOUNTED=true
    LOGMSG "/data already mounted."
else
    # Try mounting /data — find the userdata partition dynamically
    USERDATA_DEV=""
    for candidate in /dev/block/bootdevice/by-name/userdata /dev/block/by-name/userdata; do
        if [ -e "$candidate" ]; then
            USERDATA_DEV="$candidate"
            break
        fi
    done

    if [ -z "$USERDATA_DEV" ]; then
        # Fallback: scan by partition name from fstab or common UFS paths
        for dev in /dev/block/sda34 /dev/block/sda35; do
            if [ -b "$dev" ]; then
                USERDATA_DEV="$dev"
                break
            fi
        done
    fi

    if [ -n "$USERDATA_DEV" ]; then
        # Try f2fs first (most common on modern Xiaomi), then ext4
        if mount -t f2fs "$USERDATA_DEV" /data 2>/dev/null; then
            DATA_MOUNTED=true
            LOGMSG "/data mounted as f2fs from $USERDATA_DEV"
        elif mount -t ext4 "$USERDATA_DEV" /data 2>/dev/null; then
            DATA_MOUNTED=true
            LOGMSG "/data mounted as ext4 from $USERDATA_DEV"
        else
            LOGMSG "WARNING: Could not mount /data from $USERDATA_DEV"
        fi
    else
        LOGMSG "WARNING: Could not find userdata partition device"
    fi
fi

if [ "$DATA_MOUNTED" = true ]; then
    # Create the COW overflow directory that update_engine needs
    mkdir -p /data/gsi/ota
    chmod 0750 /data/gsi/ota
    LOGMSG "/data/gsi/ota/ created for COW image overflow — Error 7 prevented!"
else
    LOGMSG "WARNING: /data not mounted! If super partition overflows, Error 7 may occur."
    LOGMSG "WARNING: User should format data before flashing ROM if this happens."
fi

LOGMSG "---$SCRIPT_NAME end---"
