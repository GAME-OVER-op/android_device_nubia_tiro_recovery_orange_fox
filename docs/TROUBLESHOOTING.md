# Troubleshooting

## Build fails during source synchronization

Retry the workflow first. OrangeFox/TWRP synchronization spans many Git
repositories and transient network failures are possible.

For local builds:

```bash
FOX_SRC=/work/fox_12.1 ./scripts/sync_fox.sh
```

then rerun:

```bash
FOX_SRC=/work/fox_12.1 OUT_DIR=/work/out ./scripts/build_local.sh
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

## OrangeFox sync says `patch-manifest-fox_12.1.diff` is missing

The official OrangeFox sync helper resolves its bundled patch directory from
the process working directory (`$PWD`). It must therefore be executed from the
root of the cloned `OrangeFox/sync` repository.

This repository's `scripts/sync_fox.sh` already does that. If an older checkout
shows a path like `<your-repository>/patches/patch-manifest-fox_12.1.diff`, update
`scripts/sync_fox.sh` or run the helper from inside `orangefox-sync/`. Do not copy
the upstream patch into the device-tree `patches/` directory; that only masks
the incorrect working directory.

