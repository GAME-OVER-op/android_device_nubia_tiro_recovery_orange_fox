#!/system/bin/sh

printf '%s\n' '=== Red Magic recovery haptics probe ==='
for node in /dev/input/event*; do
    [ -e "$node" ] || continue
    name="$(cat /sys/class/input/$(basename "$node")/device/name 2>/dev/null)"
    case "$name" in
        *haptic*|*Haptic*|*vibra*|*Vibra*|*awinic*|*Awinic*|*aw869*)
            echo "$node : $name"
            getevent -il "$node" 2>/dev/null | sed -n '1,50p'
            ;;
    esac
done

echo
echo 'Expected Tiro backend:'
echo '  awinic_haptic via evdev Force Feedback'
echo '  preferred effect: FF_RUMBLE'
echo '  compatibility fallback: FF_CONSTANT'

echo
echo 'Legacy sysfs paths (diagnostic only):'
for f in \
    /sys/class/timed_output/vibrator/cont \
    /sys/class/timed_output/vibrator/enable \
    /sys/class/leds/vibrator/duration \
    /sys/class/leds/vibrator/activate; do
    [ -e "$f" ] && echo "$f : present" || echo "$f : missing"
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
    echo 'No shell sysfs test is used on Tiro: the driver exposes evdev FF, not a writable timed_output/cont node.'
    echo 'Use an evdev FF_RUMBLE tester against the awinic_haptic event node.'
fi
