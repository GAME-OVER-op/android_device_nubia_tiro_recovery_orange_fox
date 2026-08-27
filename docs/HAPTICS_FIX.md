# Haptics Fix

## Symptoms addressed

The original recovery had a roughly five-second delay after every tap because
OrangeFox could synchronously wait for a Xiaomi-specific vibrator Binder service
that does not exist on Tiro.

After moving to direct input force-feedback the five-second delay disappeared,
but device testing showed a second issue: vibration could be missing on some
UI taps and could feel different after a recovery-to-recovery reboot.

## Tiro hardware path

The Red Magic kernel loads Nubia's `haptic.ko` (`drivers/misc/haptic_hv`) and
registers the input device `awinic_haptic`. Runtime logs identify the active
implementation as the AW8692x path.

That driver requests:

```text
haptic_ram.bin
```

about eight seconds after initialization. The known-good recovery ramdisk does
not contain that Tiro firmware, so the request fails. Input `FF_CONSTANT` is
still accepted by the driver, but its implementation switches to
`AW_RAM_LOOP_MODE`; therefore it is not the best primary recovery feedback path
when RAM waveforms were never initialized.

The old Xiaomi `si_haptic.ko`, `xiaomi_touch.ko`, and `nt38771_touch.ko` files
are not restored. They were built for a different kernel and logged
`module_layout`/`Exec format error` on Tiro.

## Stable recovery solution

`scripts/patch_haptics.py` now uses this order:

```text
UI tap
  -> /sys/class/timed_output/vibrator/cont   (native Nubia continuous mode)
     -> POSIX timer stops it after timeout; GUI thread never sleeps
  -> persistent /dev/input/eventX FF effect  (secondary fallback)
  -> generic OrangeFox sysfs vibrator paths  (last fallback)
```

Nubia's `cont` sysfs handler calls the chip's continuous-mode configuration
directly and does not check `ram_init`, so it does not depend on
`haptic_ram.bin`. This makes it suitable for short recovery UI feedback.

The input-FF fallback also keeps the driver's single FF slot and updates it on
subsequent taps instead of deleting/recreating an effect every time.

The Xiaomi AIDL safety fix remains: any accidental AIDL path uses the
non-blocking `AServiceManager_checkService()` lookup rather than
`AServiceManager_getService()`.

## Why no fake `haptic_ram.bin`

The ramdisk contains Xiaomi-derived `aw8697_haptic.bin`, but Tiro is using the
AW8692x implementation. Although the file format has a compatible checksum
header, that is not proof that its waveform table is correct for the Tiro
actuator. The project deliberately does **not** rename or copy that blob to
`haptic_ram.bin`.

A genuine stock Tiro `haptic_ram.bin` can be added later if extracted from the
phone/vendor firmware and verified. The recovery UI haptics no longer depend on
it.

## Diagnostics

From recovery ADB shell:

```bash
/system/bin/tiro-haptics-debug.sh
```

For a deliberate 50 ms continuous-mode hardware test:

```bash
/system/bin/tiro-haptics-debug.sh --test
```

Useful log markers after the fix:

```text
TIRO: using firmware-independent Awinic continuous haptics
```

The existing `haptic_ram.bin` load errors may remain until the genuine Nubia
firmware is supplied; they should no longer determine whether recovery button
feedback works.
