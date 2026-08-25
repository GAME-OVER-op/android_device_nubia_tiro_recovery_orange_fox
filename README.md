# Red Magic 9 Pro / 9S Pro (NX769J, `tiro`) Recovery

Source-build project for a flashable OrangeFox/TWRP-style `recovery.img` for the
nubia Red Magic 9 Pro / 9S Pro (`NX769J`, codename `tiro`).

The project is intentionally based on a **known-good recovery userspace that has
already been tested on Red Magic 9 Pro**. The reference recovery boots, decrypts
`/data`, accepts the device PIN/password, mounts storage and dynamic partitions,
and otherwise works correctly. The only observed defect is a roughly five-second
delay on each tap-triggered action.

This repository fixes that defect **without disabling vibration**.

## What the build produces

GitHub Actions publishes:

```text
recovery.img
recovery.img.sha256
build-info.txt
```

`recovery.img` is the directly flashable image. No installer ZIP is required.

## Target image layout

| Property | Value |
|---|---|
| Device | nubia Red Magic 9 Pro / 9S Pro |
| Model | NX769J |
| Codename | tiro |
| Recovery partition | 100 MiB / 104857600 bytes |
| Android boot header | v4 |
| Ramdisk | LZ4 |
| Pixel format | RGBX_8888 |
| Kernel inside recovery.img | **No** |
| A/B recovery partition | Yes |
| FBE metadata decryption | Enabled |
| Fastbootd | Enabled |
| Haptics | Enabled, direct Linux input FF with sysfs fallback |

The empty kernel payload is intentional. The supplied known-good image also has
no kernel in its recovery image. Recovery therefore continues to use the
kernel/vendor-boot environment supplied by the device instead of embedding a
potentially mismatched kernel.

## Why the five-second tap delay happens

The known-good userspace enables a Xiaomi-specific AIDL vibrator instance:

```text
android.hardware.vibrator.IVibrator/vibratorfeature
```

On Red Magic this service is not the native recovery haptics path. A synchronous
Binder service lookup from the UI haptics path can therefore wait for the
service on every tap, producing the repeated delay.

This project patches `minuitwrp/events.cpp` to:

1. probe `/dev/input/event*` for a haptics force-feedback device;
2. prefer `FF_CONSTANT`, which is exposed by `qcom-hv-haptics` on SM8650;
3. play short vibration effects directly through `EVIOCSFF` / `EV_FF`;
4. cache the haptics file descriptor after discovery;
5. fall back to the existing sysfs vibrator paths if input FF is unavailable;
6. replace the blocking AIDL lookup with `AServiceManager_checkService()` as a
   safety net.

Haptics are **not** disabled with `TW_NO_HAPTICS`.

## Why the decryption stack is preserved

The first source build deliberately preserves the KeyMint/Gatekeeper/QSEE/FBE
components from the working reference recovery. They were compared with the
supplied unpacked ramdisk and the critical files match byte-for-byte.

This is more conservative than replacing a proven decryption chain just to make
the tree look device-pure. See `reference/WORKING_DECRYPT_STACK.txt`.

## Build with GitHub Actions

1. Push this repository to GitHub.
2. Open **Actions**.
3. Select **Build flashable recovery.img**.
4. Choose **Run workflow**.
5. After a successful build, download the artifact named approximately:

```text
RedMagic9Pro-tiro-recovery-<commit>
```

The artifact contains the flashable `recovery.img`.

The hosted-runner build also targets a **16 GiB swapfile** immediately before
compilation. To avoid trading an OOM for a disk-full failure, the swap helper
keeps roughly 18 GiB free for Android build output and automatically reduces
the swap size when required. During `mka`, a 60-second heartbeat reports RAM,
swap, disk usage and active Soong/Ninja processes so long dependency-graph
phases do not look like silent hangs.

A tag matching `v*` also starts a build automatically.

## Local build

A Linux host with enough disk space is required. OrangeFox's minimal source tree
is still large.

```bash
./scripts/build_local.sh
```

The result is written to:

```text
dist/recovery.img
```

For a separate source/output location:

```bash
FOX_SRC=/work/fox_14.1 OUT_DIR=/work/out ./scripts/build_local.sh
```

## Flashing

Back up the stock recovery first. Confirm the exact device is `NX769J` / `tiro`
before flashing.

Check the current slot:

```bash
fastboot getvar current-slot
```

On an A/B device the physical partitions are normally `recovery_a` and
`recovery_b`. Flash only after confirming the partition names on the device.
For example:

```bash
fastboot flash recovery_a recovery.img
fastboot flash recovery_b recovery.img
```

Some fastboot implementations accept the logical unsuffixed name and apply the
current slot automatically:

```bash
fastboot flash recovery recovery.img
```

Do not use partition commands blindly; verify the partition layout first.

## Important compatibility choice

The first version prioritizes reproducing the **already working** recovery over
a broad refactor. The device tree therefore contains a compatibility snapshot
of the working recovery's QTI/decryption userspace and some legacy vendor files.
The Xiaomi AIDL haptics path is disabled, but unrelated working pieces are not
removed until the source-built image is validated on hardware.

After the first source-built image is verified, vendor-specific cleanup can be
done incrementally without risking `/data` decryption.

## Repository layout

```text
.github/workflows/build-recovery.yml   GitHub Actions build
device/nubia/tiro/                     recovery device tree + compatibility blobs
scripts/patch_haptics.py               non-blocking input-FF haptics source patch
scripts/sync_fox.sh                    OrangeFox source synchronization
scripts/prepare_source.sh              install tree + patch source
scripts/build_local.sh                 local build entry point
scripts/verify_recovery.sh             output image checks
reference/                             known-good image and upstream notes
docs/                                  architecture/build/CI/troubleshooting notes
```

## Upstream

The workflow uses OrangeFox 14.1's official sync tooling. Nubia SM8650 sources
are used as hardware references and are listed in `reference/UPSTREAM_SOURCES.txt`.
The flashable recovery image does not embed the Lineage kernel.

## License and proprietary components

Project-authored scripts/documentation are licensed under Apache-2.0. Files
copied from upstream projects retain their original notices. The compatibility
blob snapshot includes vendor/OEM binaries whose redistribution may be governed
by their respective owners' terms; they are not relicensed by this repository.
See `THIRD_PARTY.md`.
