#!/system/bin/sh

echo "=== Red Magic recovery haptics probe ==="
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
echo "Binder vibrator services (diagnostic only):"
service list 2>/dev/null | grep -i vibrator || true
