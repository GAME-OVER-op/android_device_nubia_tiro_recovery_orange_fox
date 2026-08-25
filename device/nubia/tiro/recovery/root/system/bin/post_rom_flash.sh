#!/system/bin/sh

SCRIPT_NAME="$(basename "$0")"

LOGMSG() {
    echo "I:$@" >> /tmp/recovery.log
}

LOGMSG "---$SCRIPT_NAME start---"

# Kill the background symlink daemon spawned by pre_rom_flash.sh
if [ -f /tmp/fox_symlink_daemon.pid ]; then
    DAEMON_PID=$(cat /tmp/fox_symlink_daemon.pid)
    LOGMSG "Stopping symlink daemon (PID $DAEMON_PID)..."
    kill -9 "$DAEMON_PID" 2>/dev/null
    rm -f /tmp/fox_symlink_daemon.pid
    LOGMSG "Symlink daemon stopped."
fi

LOGMSG "Restoring recovery.img..."
slot="$(getprop ro.boot.slot_suffix)"
if [ -f /tmp/fox_backup.img ]; then
    dd if="/tmp/fox_backup.img" of="/dev/block/bootdevice/by-name/recovery${slot}" bs=1M
    rm -f /tmp/fox_backup.img
    sync
    LOGMSG "Recovery restored to active slot ($slot) successfully."
else
    LOGMSG "No recovery backup found to restore!"
fi

LOGMSG "---$SCRIPT_NAME end---"
