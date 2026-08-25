# Haptics Fix

## Symptom

Every tap is received, but the corresponding action appears about five seconds
later. Multiple fast taps are queued and then executed one by one with the same
roughly five-second interval. The behavior is visible even on the password/PIN
keyboard.

That pattern is inconsistent with a slow touchscreen or low frame rate. It is a
synchronous per-action wait.

## Root cause

The reference tree enabled:

```make
TW_SUPPORT_INPUT_AIDL_HAPTICS := true
TW_SUPPORT_INPUT_AIDL_HAPTICS_FQNAME := "IVibrator/vibratorfeature"
TW_SUPPORT_INPUT_AIDL_HAPTICS_FIX_OFF := true
```

OrangeFox 12.1's `minuitwrp/events.cpp` resolves that vibrator service from the
UI vibration path. A blocking service lookup is inappropriate when the device's
recovery environment does not provide that exact Xiaomi service.

## Fix used here

The project keeps haptics enabled but does not enable the Xiaomi AIDL haptics
build flags. `scripts/patch_haptics.py` adds a direct Linux input
force-feedback backend to minuitwrp.

The Red Magic SM8650 kernel source config enables `qcom-hv-haptics`, and its
driver registers an input device named:

```text
qcom-hv-haptics
```

with `FF_CONSTANT` support.

At runtime:

```text
UI tap
  -> minuitwrp vibrate()
     -> cached /dev/input/eventX haptics device
        -> EVIOCSFF (FF_CONSTANT)
        -> EV_FF play
     -> immediate return
```

If no suitable input FF device exists, the old sysfs vibrator implementation is
used as fallback. If AIDL is accidentally enabled later, the patch changes the
service lookup to the non-blocking `AServiceManager_checkService()` call.

## Diagnostics in recovery

The ramdisk includes:

```bash
/system/bin/tiro-haptics-debug.sh
```

Run it from ADB shell to list candidate haptics input nodes and supported FF
capabilities.

Useful manual checks:

```bash
getevent -il /dev/input/event* | grep -A8 -i 'haptic\|vibra'
logcat -d | grep -iE 'vibrator|haptic|Waiting for service'
grep -iE 'vibrator|haptic' /tmp/recovery.log
```

Success criteria:

- no repeated `Waiting for service ... vibrator` messages;
- buttons react immediately;
- PIN/password characters appear immediately;
- short vibration feedback still works.
