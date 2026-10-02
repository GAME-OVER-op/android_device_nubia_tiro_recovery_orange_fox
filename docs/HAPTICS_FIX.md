# Haptics Fix

## Symptoms addressed

The original recovery could pause for several seconds after taps because a
Xiaomi-specific vibrator Binder service was queried synchronously even though
that service is not Tiro's native haptics path. A later Tiro patch removed the
delay but incorrectly preferred `FF_CONSTANT`, and recovery stopped physically
vibrating even though the input device still accepted the ioctl.

## Verified Tiro hardware path

The Red Magic kernel loads Nubia's `haptic_hv` driver and registers the input
device `awinic_haptic`. Runtime probing on the phone reports these Force
Feedback capabilities:

```text
FF_RUMBLE
FF_PERIODIC
FF_CONSTANT
FF_CUSTOM
FF_GAIN
```

A direct root-terminal evdev test uploaded an `FF_RUMBLE` effect to the live
`awinic_haptic` event node, played it, and produced physical vibration. This is
the hardware-verified recovery path.

The driver also requests `haptic_ram.bin`, which is absent from the recovery
firmware search paths. That request fails repeatedly. `FF_RUMBLE` still works
without that blob, so short recovery UI feedback does not need a guessed or
renamed waveform firmware.

The device does **not** expose a writable runtime
`/sys/class/timed_output/vibrator/cont` node. The `aw8692x_cont_*` files visible
under `of_node` are Device Tree properties, not runtime haptics controls.

## Stable recovery solution

`scripts/patch_haptics.py` now uses this order:

```text
UI tap
  -> persistent awinic_haptic evdev effect
       -> FF_RUMBLE first (verified on Tiro)
       -> FF_CONSTANT only if a different kernel lacks FF_RUMBLE
  -> generic OrangeFox sysfs vibrator paths
```

One FF slot is retained and updated. Before a repeated tap, an in-flight effect
is stopped and then retriggered, avoiding repeated allocation/deallocation and
giving deterministic feedback for fast UI input.

The Xiaomi AIDL safety fix remains: an accidental AIDL path uses the
non-blocking `AServiceManager_checkService()` lookup instead of
`AServiceManager_getService()`.

## Why no fake `haptic_ram.bin`

The ramdisk contains Xiaomi-derived `aw8697_haptic.bin`, while the active Tiro
implementation is AW8692x. A compatible-looking header is not proof that its
waveforms are correct for this actuator. The project therefore does not rename
or copy that file to `haptic_ram.bin`.

A genuine Tiro `haptic_ram.bin` may be added later only if it is extracted from
matching Nubia firmware and verified. Recovery UI vibration already works via
`FF_RUMBLE` without it.

## Diagnostics

From recovery ADB shell:

```bash
/system/bin/tiro-haptics-debug.sh
```

Expected recovery log markers are:

```text
Using input FF haptics device 'awinic_haptic' ... (effect=FF_RUMBLE)
TIRO: active recovery haptics backend is input FF_RUMBLE
```

`haptic_ram.bin` load errors can remain until genuine Nubia firmware is
supplied; they are not required for the verified `FF_RUMBLE` feedback path.
