# Build Notes

## Source base

OrangeFox 12.1 is synchronized through the project's official `sync` helper.
That helper currently uses the TWRP 12.1 minimal manifest, patches the build
system for OrangeFox, and fetches the OrangeFox recovery core and vendor tree.

## Build target

```bash
lunch twrp_tiro-eng
mka adbd recoveryimage
```

Expected product output:

```text
$OUT_DIR/target/product/tiro/recovery.img
```

## Why the kernel is not built

The known-good image is a header-v4 recovery image with an empty kernel section.
The device's recovery partition is therefore a recovery ramdisk image, not a
standalone replacement kernel image.

Building the Lineage kernel and embedding it would change the boot model and
could introduce module/vendor_boot ABI mismatches. The kernel repositories are
kept as hardware references only.

## Clean minuitwrp output

`prepare_source.sh` removes stale recovery-root/minuitwrp outputs before the
build. This is intentional: OrangeFox/TWRP incremental builds can otherwise
leave an older relinked `libminuitwrp.so` in the recovery ramdisk even after the
source haptics code was changed.

## Image verification

`verify_recovery.sh` checks:

- Android boot image magic;
- image does not exceed the 100 MiB recovery partition;
- SHA-256;
- AVB information when `avbtool` is available;
- compiled `libminuitwrp.so` does not contain the Xiaomi vibratorfeature
  instance string;
- critical decryption files are present in the final recovery root.
