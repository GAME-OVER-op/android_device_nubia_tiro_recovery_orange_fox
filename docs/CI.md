# Continuous Integration

The repository ships with a GitHub Actions workflow that produces a flashable
`recovery.img` for `nubia tiro / NX769J`.

## Resource policy

OrangeFox 12.1 synchronization is disk-heavy. The workflow therefore:

- removes large preinstalled SDK/toolchain directories that are not needed by
  the Android recovery build;
- disables ccache on GitHub-hosted runners because a one-shot runner cannot
  reuse it and an 8 GiB cache would only reduce available build space;
- limits the final build to two parallel jobs to reduce peak memory pressure;
- keeps OrangeFox synchronization pinned to a known sync-helper revision;
- validates the bundled compatibility tree and haptics patch before the large
  source synchronization starts.

For self-hosted runners, `BUILD_JOBS` and `SYNC_JOBS` can be raised when enough
RAM and storage are available.

## Output contract

A successful run uploads one artifact containing:

```text
recovery.img
recovery.img.sha256
build-info.txt
```

The workflow fails instead of publishing an image when any of these conditions
is detected:

- Android boot-image magic is missing;
- the image exceeds the 100 MiB recovery partition;
- required KeyMint/Gatekeeper/FBE compatibility files are missing;
- the compiled minuitwrp library still contains the Xiaomi
  `IVibrator/vibratorfeature` instance used by the blocking haptics path.
