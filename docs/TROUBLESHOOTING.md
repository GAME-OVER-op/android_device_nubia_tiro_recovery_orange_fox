# Troubleshooting

## Build fails during source synchronization

Retry the workflow first. OrangeFox/TWRP synchronization spans many Git
repositories and transient network failures are possible.

For local builds:

```bash
FOX_SRC=/work/fox_14.1 ./scripts/sync_fox.sh
```

then rerun:

```bash
FOX_SRC=/work/fox_14.1 OUT_DIR=/work/out ./scripts/build_local.sh
```

## GitHub runner runs out of disk space

The workflow removes several large preinstalled SDK/toolchain directories
before synchronization. If GitHub changes its hosted-runner image and free disk
becomes insufficient, use a larger self-hosted runner and keep the same build
scripts.

## Image builds but tapping still waits several seconds

Inspect the built library, not only the source tree:

```bash
strings out/target/product/tiro/recovery/root/system/lib64/libminuitwrp.so | \
  grep -iE 'vibratorfeature|AServiceManager_getService|TIRO_INPUT'
```

Also run in recovery:

```bash
/system/bin/tiro-haptics-debug.sh
logcat -d | grep -iE 'vibrator|haptic|Waiting for service'
```

The output library must not be an old incrementally relinked copy.

## Haptics no longer delay the UI but do not vibrate

Check whether the kernel exposes force feedback:

```bash
getevent -il /dev/input/event* | grep -A8 -i 'haptic\|vibra'
```

For the expected Qualcomm path, look for:

```text
Name="qcom-hv-haptics"
FF_CONSTANT
```

If the node does not exist in the booted recovery environment, the next step is
to determine whether the matching stock vendor_boot recovery module set is being
loaded. Do not blindly insert modules built against a different kernel ABI.

## /data decryption regresses

Do not replace the compatibility KeyMint/Gatekeeper/QSEE blobs first. Compare
the final recovery root against `reference/recovery-root.sha256` and confirm
that `prepdecrypt.sh`, QSEE, KeyMint and Gatekeeper services are present.

## OrangeFox sync says `patch-manifest-fox_14.1.diff` is missing

The official OrangeFox sync helper resolves its bundled patch directory from
the process working directory (`$PWD`). It must therefore be executed from the
root of the cloned `OrangeFox/sync` repository.

This repository's `scripts/sync_fox.sh` already does that. If an older checkout
shows a path like `<your-repository>/patches/patch-manifest-fox_14.1.diff`, update
`scripts/sync_fox.sh` or run the helper from inside `orangefox-sync/`. Do not copy
the upstream patch into the device-tree `patches/` directory; that only masks
the incorrect working directory.

## `TOP: unbound variable` / `/device/nubia/tiro/vendorsetup.sh` not found

If `source build/envsetup.sh` fails with:

```text
build/envsetup.sh: ...: TOP: unbound variable
...
/device/nubia/tiro/vendorsetup.sh: No such file or directory
```

the shell entered the Android build environment with Bash `nounset` (`set -u`)
enabled. AOSP/OrangeFox `envsetup.sh` is not nounset-safe and intentionally
references some variables before initialization. Once `gettop()` aborts, its
empty result causes device paths to be resolved from `/` instead of the source
tree.

The bundled workflow and `scripts/build_local.sh` deliberately execute
`set +u` immediately before `source build/envsetup.sh` and keep nounset disabled
for `lunch`/`mka`. Do not remove that line. `errexit` and `pipefail` remain
enabled, so actual build failures still stop the job.


### envsetup exits with code 1 after OrangeFox setup

OrangeFox/AOSP `build/envsetup.sh` is intended to be sourced from an interactive shell. A harmless final optional `[ -s ... ]` probe can return 1 even after the environment was configured successfully. The project therefore disables `errexit` only for the source operation, captures the status, restores `set -e`, and validates `lunch`, `mka`, and `gettop` before continuing.

## `BOARD_SYSTEMSDK_VERSIONS (32)` is lower than `PRODUCT_SHIPPING_API_LEVEL`

This error means the project was synchronized against **fox_12.1**. Do not lower the device API to 32. The known-good recovery is SDK 34 and its original tree targets the OrangeFox 14.1 build-variable set. Remove the old source checkout/cache and sync again with:

```bash
FOX_SRC=/work/fox_14.1 ./scripts/sync_fox.sh
```

The project must retain API/VNDK 34 and build on fox_14.1. A fox_12.1 image may compile after forcing API values to 32 but can stop at the OrangeFox splash at runtime.


## `Only whole numbers can be used for FOX_MAINTAINER_PATCH_VERSION`

OrangeFox 14.1 validates `FOX_MAINTAINER_PATCH_VERSION` with `printf %d` and rejects hashes or other non-decimal strings. Do not pass a Git commit prefix such as `a7f852ef` here.

This project uses GitHub Actions `GITHUB_RUN_NUMBER` as the maintainer patch version. Local builds default to `0`; an explicitly supplied `TIRO_BUILD_VERSION` must contain decimal digits only. The project commit SHA is recorded separately in `build-info.txt`, so no traceability is lost.
