# Final Red Magic 9 Pro cleanup

This cleanup is based on the on-device recovery/logcat validation from the
working `tiro` build.

## Visible post-flash buttons and labels

The known-good Red Magic ramdisk uses the native OrangeFox compact button
styles `btn_raised_s` and `btn_raised_s_hl`. The style supplies both the font
and the background image/shape.

A synced fox_14.1 theme can miss one side of that style/resource chain and emit:

```
E:No image resource or fill specified for button
```

An intermediate tiro workaround placed `<image resource=...>` directly inside
the six buttons on `flash_done` and `flash_image_done`. That restored the button
backgrounds on-device, but it also caused their labels to disappear.

The final fix keeps the page XML in the same native form as the known-good
ramdisk:

- 4 × `style="btn_raised_s"`
- 2 × `style="btn_raised_s_hl"`
- no explicit child `<image>` on those buttons
- the button `<text>` nodes remain intact

`patch_theme_button_resources.py` now repairs both halves of the theme chain:

- `styles.xml`: compact styles, `Secondary` font, native text colors, image reference
- `images.xml`: matching compact shape resources

This preserves the native OrangeFox drawing order so the background and label
are both rendered.

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
Goodix/input for touch and the native Nubia/Awinic continuous-mode sysfs path
for primary haptics, with `awinic_haptic` input force-feedback as fallback.

No KeyMint, Gatekeeper, QSEE, FBE/decryption, App Manager or Root Module Manager
components were changed by this cleanup.

## fox_14.1 compact post-flash button resource guard

The tiro install-page overlay uses `btn_raised_s` and `btn_raised_s_hl`. The
known-good ramdisk provides both complete style definitions and both matching
shape resources. A synced fox_14.1 theme snapshot can omit or incompletely
define either side of that chain.

`prepare_source.sh` runs `patch_theme_button_resources.py`. It repairs only the
missing/incomplete compact style definitions and shape resources; it does **not**
replace the current theme with an older full theme. CI checks the prepared
source, and `verify_recovery.sh` validates the built style -> font/image ->
shape chain plus the six button labels.

## Dalvik-only post-flash localization

Tiro has no usable `/cache` partition, so the post-flash action is Dalvik-only.
The device overlay uses four Tiro-specific language keys instead of inventing
an unresolved inline fallback. `patch_dalvik_language_resources.py` injects
those keys into every OrangeFox language XML at source-preparation time, using
existing localized Dalvik strings where available. This removes the runtime
`String resource 'wipe_dalvik_btn' not found` error without reintroducing a
`/cache` wipe.

## USB gadget startup ordering

The October 2026 on-device logs showed two independent init actions handling the
plain `adb` configuration: the base recovery `/system/etc/init/hw/init.rc` and
the device `init.recovery.usb.rc`. Both tried to link `ffs.adb` and bind `g1/UDC`,
which produced `File exists` and `Device or resource busy` races.

Tiro now leaves the plain ADB gadget action to the base recovery init. The
device rc still owns Tiro-specific MTP, sideload and fastboot modes, but it waits
up to five seconds for `/sys/class/udc/${ro.boot.usbcontroller}` before setting
`sys.usb.config=adb`. The old early `on boot` ADB request was removed from
`init.recovery.qcom.rc`, and the unused `g2` gadget directory setup was removed
so only the actually configured `g1` gadget is created.

## QSEE / Gatekeeper ordering

The first Gatekeeper process used to start in `early-init`, before qseecomd had
registered its secure listeners, and aborted with signal 6. Later Gatekeeper
starts succeeded and FBE decrypted normally. Gatekeeper is now started once,
from `vendor.sys.listeners.registered=true`, next to the working QTI KeyMint
start. This preserves the proven decrypt stack while removing the deterministic
early crash.

## ueventd parser cleanup

The bundled vendor `ueventd.rc` contained three malformed `/sys` rules, a stray
`*/` token, a duplicate `dma_heap` subsystem declaration, and an import of an
unbundled `ueventd.qcom.userdebug.rc`. These generated parser errors on every
boot and could prevent intended permissions from being applied.

The `/sys` rules now use the `nodename attribute mode uid gid` form, the stale
import/token were removed, and `dma_heap` is left to the base system ueventd
configuration. Static and built-image verification now reject malformed Tiro
`/sys` rules.

## Tiro-only fstab and install-page cleanup

The Xiaomi-only `mi_ext` entries were removed from `recovery.fstab`; NX769J has
no such logical partition and OrangeFox was probing it twice on every boot. The
install-page `auto_dfe_chk` reference now carries a readable fallback label so
missing upstream language resources cannot produce an unresolved-string error.

