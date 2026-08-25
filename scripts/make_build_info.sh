#!/usr/bin/env bash
set -euo pipefail

IMG="${1:?Usage: make_build_info.sh <recovery.img> <output-file> [fox-source]}"
OUT="${2:?Missing output file}"
FOX_SRC="${3:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

{
  echo "Red Magic 9 Pro Recovery Build Information"
  echo "=========================================="
  echo "device=tiro"
  echo "model=NX769J"
  echo "manufacturer=nubia"
  echo "recovery_partition_size=104857600"
  echo "boot_header_version=4"
  echo "ramdisk_compression=lz4"
  echo "kernel_in_recovery=false"
  echo "haptics_backend=input-force-feedback-with-sysfs-fallback"
  echo "build_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "project_commit=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo archive)"
  if [[ -n "$FOX_SRC" && -d "$FOX_SRC/bootable/recovery/.git" ]]; then
    echo "orangefox_recovery_commit=$(git -C "$FOX_SRC/bootable/recovery" rev-parse HEAD)"
  fi
  if [[ -n "$FOX_SRC" && -d "$FOX_SRC/vendor/recovery/.git" ]]; then
    echo "orangefox_vendor_commit=$(git -C "$FOX_SRC/vendor/recovery" rev-parse HEAD)"
  fi
  echo "image_size=$(stat -c '%s' "$IMG")"
  echo "image_sha256=$(sha256sum "$IMG" | awk '{print $1}')"
} > "$OUT"
