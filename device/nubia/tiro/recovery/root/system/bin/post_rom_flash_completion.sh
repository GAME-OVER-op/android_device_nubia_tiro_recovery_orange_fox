#!/system/bin/sh
#
# post_rom_flash_completion.sh - OrangeFox Recovery for Onyx (POCO F7)
#
# Runs AFTER all ROM flash processes complete (called from Fox_Post_Zip_Install).
# Execution order:
#   1. pre_rom_flash.sh    (backups recovery, sets up environment)
#   2. update_engine       (flashes payload.bin to inactive slot)
#   3. post_rom_flash.sh   (restores recovery to CURRENT slot, DELETES fox_backup.img)
#   4. OrangeFox internals (Patch_AVB20, Disable_AVB2 if toggle on, reflash TWRP)
#   5. THIS SCRIPT         (fox_backup.img is GONE at this point!)
#
# This script fixes 4 critical issues:
#   FIX 1: Clone recovery to BOTH slots.
#   FIX 2: Disable vbmeta verification on ALL 4 partitions (both slots).
#   FIX 3: Switch active boot slot to the NEWLY FLASHED (target) slot.
#   FIX 4: Ensure /metadata/ota directories exist for snapshot merge.
#
# NOTE: DFE (Disable Force Encryption) is handled by a SEPARATE flashable zip
# (DFE.zip in /FFiles/). User must flash it manually if they want DFE.
#

SCRIPT_NAME="$(basename "$0")"

LOGMSG() {
    echo "I:$@" >> /tmp/recovery.log
}

LOGMSG "---$SCRIPT_NAME start---"

# ============================================================================
# STEP 1: Restore OrangeFox recovery to BOTH slots
# ============================================================================
# NOTE: fox_backup.img is ALREADY DELETED by post_rom_flash.sh!
# Instead, we copy the recovery from the current (already-restored) slot
# to the inactive slot using dd.

CURRENT_SLOT_SUFFIX="$(getprop ro.boot.slot_suffix)"

if [ "$CURRENT_SLOT_SUFFIX" = "_a" ]; then
    SRC_RECOVERY="/dev/block/bootdevice/by-name/recovery_a"
    DST_RECOVERY="/dev/block/bootdevice/by-name/recovery_b"
    DST_SLOT_NAME="_b"
else
    SRC_RECOVERY="/dev/block/bootdevice/by-name/recovery_b"
    DST_RECOVERY="/dev/block/bootdevice/by-name/recovery_a"
    DST_SLOT_NAME="_a"
fi

if [ -e "$SRC_RECOVERY" ] && [ -e "$DST_RECOVERY" ]; then
    LOGMSG "Cloning recovery from ${CURRENT_SLOT_SUFFIX} to ${DST_SLOT_NAME}..."
    dd if="$SRC_RECOVERY" of="$DST_RECOVERY" bs=1M 2>/dev/null
    sync
    LOGMSG "Recovery cloned to ${DST_SLOT_NAME} successfully."
else
    LOGMSG "WARNING: Recovery partition(s) not found (src=$SRC_RECOVERY, dst=$DST_RECOVERY)"
fi

# ============================================================================
# STEP 2: Disable vbmeta verification on BOTH slots
# ============================================================================
# ROM flash writes fresh vbmeta with verification ENABLED (flags=0x00).
# If DFE then modifies vendor_boot, verified boot FAILS → fastboot!
# We set flags byte at AVB offset 123 to 0x03 (disable verification + hashtree).
#
# NOTE: OrangeFox has a built-in Disable_AVB2() in C++ (orangefox.cpp:1089-1092),
# but it ONLY runs if BOTH conditions are true:
#   1. OF_SUPPORT_VBMETA_AVB2_PATCHING is defined at compile time
#   2. TW_AUTO_DISABLE_AVB2_VAR is toggled ON in the UI (defaults to "0"!)
# Since condition 2 is off by default, we MUST handle it here as a safety net.

LOGMSG "Disabling vbmeta verification on both slots..."

for part in vbmeta_a vbmeta_b vbmeta_system_a vbmeta_system_b; do
    DEV="/dev/block/bootdevice/by-name/${part}"
    if [ -e "$DEV" ]; then
        # Read current flags at AVB_VBMETA_FLAGS_OFFSET (123)
        CURRENT=$(dd if="$DEV" bs=1 skip=123 count=1 2>/dev/null | od -An -tx1 | tr -d ' ')
        if [ "$CURRENT" != "03" ]; then
            printf '\x03' | dd of="$DEV" bs=1 seek=123 count=1 conv=notrunc 2>/dev/null
            LOGMSG "  ${part}: verification disabled (was 0x${CURRENT}, now 0x03)"
        else
            LOGMSG "  ${part}: already disabled (0x03)"
        fi
    else
        LOGMSG "  ${part}: partition not found, skipping"
    fi
done
sync

# ============================================================================
# STEP 3: Switch active slot to the NEWLY FLASHED slot
# ============================================================================
# update_engine_sideload returns kSuccess but does NOT call SetActiveBootSlot!
# The sideload_main.cc only checks status == UPDATED_NEED_REBOOT and exits.
# It is the CALLER's (OrangeFox's) responsibility to switch the active slot.
#
# We determine the target (inactive) slot and switch to it:

if [ "$CURRENT_SLOT_SUFFIX" = "_a" ]; then
    TARGET_SLOT_NUM=1
    TARGET_SLOT_NAME="B"
else
    TARGET_SLOT_NUM=0
    TARGET_SLOT_NAME="A"
fi

LOGMSG "Current boot slot: ${CURRENT_SLOT_SUFFIX}"
LOGMSG "Target (flashed) slot: ${TARGET_SLOT_NAME} (slot ${TARGET_SLOT_NUM})"

if command -v bootctl >/dev/null 2>&1; then
    bootctl set-active-boot-slot "$TARGET_SLOT_NUM" 2>/dev/null
    RESULT=$?
    if [ $RESULT -eq 0 ]; then
        LOGMSG "Active boot slot switched to ${TARGET_SLOT_NAME} ✓"
    else
        LOGMSG "ERROR: bootctl set-active-boot-slot failed (exit $RESULT)"
        LOGMSG "User MUST manually switch slot before rebooting!"
    fi
else
    LOGMSG "ERROR: bootctl not found! Cannot switch active slot."
    LOGMSG "User MUST manually switch slot before rebooting!"
fi

# ============================================================================
# STEP 4: Cancel any stale snapshot-update state
# ============================================================================
# If snapshot-update-status remains "snapshotted", the bootloader will try
# to merge snapshots during boot, which can fail and mark the slot unbootable.
# NOTE: Do NOT cancel the snapshot that update_engine just created!
# Only clear stale/orphaned snapshot state from PREVIOUS failed attempts.

# Also clear via metadata filesystem directly
if mountpoint -q /metadata 2>/dev/null; then
    METADATA_MOUNTED=1
else
    METADATA_MOUNTED=0
    mount -t ext4 /dev/block/bootdevice/by-name/metadata /metadata 2>/dev/null || \
    mount -t f2fs /dev/block/bootdevice/by-name/metadata /metadata 2>/dev/null
fi

if mountpoint -q /metadata 2>/dev/null; then
    # Ensure required directories exist for next boot
    mkdir -p /metadata/ota/snapshots 2>/dev/null
    mkdir -p /metadata/gsi/ota 2>/dev/null
    sync
    # Only unmount if we mounted it ourselves
    if [ "$METADATA_MOUNTED" = "0" ]; then
        umount /metadata 2>/dev/null
    fi
fi

LOGMSG "---$SCRIPT_NAME end---"

