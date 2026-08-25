# Building

This project builds against OrangeFox **fox_14.1**, matching the Android 14 / SDK 34 profile of the known-good recovery ramdisk.

## GitHub Actions

Run **Build flashable recovery.img** from the Actions tab. The workflow synchronizes the official OrangeFox 14.1 minimal source, installs the `tiro` tree, applies the non-blocking haptics patch, builds, verifies, and uploads the image.

## Local build

```bash
export FOX_SRC=/work/fox_14.1
export OUT_DIR=/work/out
./scripts/build_local.sh
```

The effective build command is:

```bash
source build/envsetup.sh
lunch twrp_tiro-ap2a-eng
mka adbd recoveryimage
```

Java 17 is recommended for the Android 14 source tree.

## Output

```text
dist/recovery.img
dist/recovery.img.sha256
dist/build-info.txt
```
