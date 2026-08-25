# Continuous Integration

The GitHub Actions workflow builds a flashable `recovery.img` for Nubia Red Magic 9 Pro / NX769J (`tiro`).

## Source baseline

The project intentionally uses **OrangeFox `fox_14.1`**. The known-good recovery supplied for this bring-up is an Android 14 / SDK 34 recovery and its original device tree explicitly references the `fox_14.1` OrangeFox build variables. Building that tree on `fox_12.1` creates an Android 12L / SDK 32 userspace; such an image can boot far enough to show the OrangeFox splash but is not considered runtime-compatible with the proven ramdisk.

The source helper revision is pinned in `config/source-lock.env`. OrangeFox's official sync helper currently supports both 14.1 and 12.1; this project selects 14.1.

## Runtime/API profile

The product keeps the known-good Android 14 profile:

```make
PRODUCT_SHIPPING_API_LEVEL  := 34
PRODUCT_TARGET_VNDK_VERSION := 34
BOARD_SHIPPING_API_LEVEL    := 34
SHIPPING_API_LEVEL          := 34
```

The reference ramdisk reports:

```text
ro.build.version.sdk=34
ro.product.first_api_level=34
ro.board.first_api_level=34
```

## Resource policy

The workflow removes unrelated preinstalled SDK/toolchain directories, disables ccache on ephemeral hosted runners, limits build parallelism, and validates the bundled tree before the large sync. Java 17 is used for the Android 14 source build.

## Build target

The workflow uses the Android 14 release-aware lunch target:

```text
twrp_tiro-ap2a-eng
```

This follows current OrangeFox 14.1 device build practice.

## Output contract

A successful run uploads:

```text
recovery.img
recovery.img.sha256
build-info.txt
```

The workflow refuses to publish an image if the Android boot-image magic is missing, the image exceeds the 100 MiB recovery partition, critical preserved decrypt files disappear, or the blocking Xiaomi `IVibrator/vibratorfeature` path survives in the compiled minuitwrp library.

## Numeric OrangeFox patch version

`FOX_MAINTAINER_PATCH_VERSION` must be numeric. GitHub Actions maps it to `GITHUB_RUN_NUMBER`; the exact repository commit is recorded separately in `build-info.txt`.

## Memory pressure and build heartbeat

Immediately before compilation, GitHub Actions requests a **16 GiB swapfile** via
`scripts/setup_ci_swap.sh`. The script deliberately preserves about 18 GiB of
free filesystem space for Soong/Ninja output. If the hosted runner does not have
enough disk for the full 16 GiB swapfile, it automatically chooses the largest
safe size (minimum 4 GiB) and emits a workflow warning. If `swapon` is forbidden
by the runner, the build continues without failing solely because of swap setup.

During `mka`, `scripts/build_heartbeat.sh` prints a status group every 60 seconds
containing load average, RAM, swap usage, `vmstat`, disk space, active Android
build processes, and the largest memory consumers. This is intentional: Soong's
bootstrap/dependency-graph phase can remain visually at 99% for a long period
without writing normal build progress.

The repository uses `actions/checkout@v6` and `actions/upload-artifact@v6`; both run on Node.js 24.

The swapfile is removed immediately after compilation (including build-step failures via the shell trap) so artifact verification and staging regain that disk space.
