# Final Red Magic 9 Pro cleanup

This cleanup is based on the on-device recovery/logcat validation from the
working `tiro` build.

## Visible post-flash buttons

OrangeFox `GUIButton` requires a directly resolved `<image>` or `<fill>` to
obtain a non-zero render/touch rectangle. Six buttons on `flash_done` and
`flash_image_done` inherited `btn_raised_s` / `btn_raised_s_hl`, but the
background was not resolved by the constructor and produced:

```
E:No image resource or fill specified for button
```

Each of those six buttons now declares its existing theme shape explicitly:

- 4 × `btn_raised_s`
- 2 × `btn_raised_s_hl`

The appearance stays native OrangeFox; the buttons are now guaranteed to be
visible and to have the intended 320 × `%btn_h%` hit area.

## Cache on an A/B device

The inherited Xiaomi tree mapped `/cache` to a `rescue` partition. That mapping
does not exist/work on Red Magic 9 Pro and caused repeated mount errors. It was
removed from `recovery.fstab` and `twrp.flags`.

OrangeFox automatically falls back to `/data` for persistent recovery logs when
no `/cache` partition is registered. Since `/data` decryption is confirmed
working on this build, this is the correct path for `tiro`.

The two post-flash cleanup buttons now perform **Dalvik/ART cache wipe only**,
matching OrangeFox/TWRP behaviour for A/B devices without a dedicated cache
partition.

## Xiaomi-only kernel modules

The on-device log showed `Exec format error` for:

- `nt38771_touch.ko`
- `si_haptic.ko`
- `xiaomi_touch.ko`

They are no longer loaded or bundled. The working Red Magic paths remain:
Goodix/input for touch and `awinic_haptic` via Linux input force-feedback for
haptics.

No KeyMint, Gatekeeper, QSEE, FBE/decryption, App Manager or Root Module Manager
components were changed by this cleanup.

## fox_14.1 compact post-flash button resource guard

The tiro install-page overlay explicitly uses `btn_raised_s` and
`btn_raised_s_hl`.  The known-good ramdisk defines both as OrangeFox shapes,
but a synced fox_14.1 theme snapshot can omit one or both declarations from the
resource registry copied into `PRODUCT_OUT`.

`prepare_source.sh` now runs `patch_theme_button_resources.py`.  It locates the
current OrangeFox theme registry and adds only the missing compact shapes.  It
does **not** replace the current theme with the older known-good `images.xml`.
The CI verifies the prepared source before compiling and `verify_recovery.sh`
checks that the built `twres/resources/images.xml` contains both resource names.
