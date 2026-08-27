#!/system/bin/sh

CONT=/sys/class/timed_output/vibrator/cont
RAM_NUM=/sys/class/timed_output/vibrator/ram_num
RAM_UPDATE=/sys/class/timed_output/vibrator/ram_update

printf '%s\n' '=== Red Magic recovery haptics probe ==='
for node in /dev/input/event*; do
    [ -e "$node" ] || continue
    name="$(cat /sys/class/input/$(basename "$node")/device/name 2>/dev/null)"
    case "$name" in
        *haptic*|*Haptic*|*vibra*|*Vibra*|*awinic*|*Awinic*|*aw869*)
            echo "$node : $name"
            getevent -il "$node" 2>/dev/null | sed -n '1,40p'
            ;;
    esac
done

echo
echo 'Native Nubia/Awinic sysfs:'
for f in "$CONT" "$RAM_NUM" "$RAM_UPDATE"; do
    if [ -e "$f" ]; then
        echo "$f : present"
        [ -r "$f" ] && { printf '  value: '; cat "$f" 2>/dev/null || true; }
    else
        echo "$f : missing"
    fi
done

echo
echo 'Firmware files:'
for f in \
    /vendor/firmware/haptic_ram.bin \
    /lib/firmware/haptic_ram.bin \
    /vendor/firmware/aw8697_haptic.bin \
    /lib/firmware/aw8697_haptic.bin; do
    [ -e "$f" ] && ls -l "$f" || echo "$f : missing"
done

echo
echo 'Recent kernel haptics messages:'
dmesg 2>/dev/null | grep -iE 'haptic_ram|haptic_hv|awinic|aw869|ram firmware' | tail -80 || true

echo
echo 'Binder vibrator services (diagnostic only):'
service list 2>/dev/null | grep -i vibrator || true

if [ "${1:-}" = "--test" ]; then
    echo
    echo 'Continuous-mode test:'
    if [ -w "$CONT" ]; then
        echo 1 > "$CONT"
        sleep 0.05
        echo 0 > "$CONT"
        echo 'Triggered 50 ms via native cont node.'
    else
        echo 'Native cont node is not writable.'
        exit 1
    fi
fi
