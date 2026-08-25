#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FOX_SRC="${FOX_SRC:-$ROOT/.work/fox_12.1}"

[[ -d "$FOX_SRC/bootable/recovery" ]] || { echo "Missing OrangeFox source: $FOX_SRC" >&2; exit 2; }

mkdir -p "$FOX_SRC/device/nubia"
rm -rf "$FOX_SRC/device/nubia/tiro"
cp -a "$ROOT/device/nubia/tiro" "$FOX_SRC/device/nubia/tiro"

python3 "$ROOT/scripts/patch_haptics.py" "$FOX_SRC/bootable/recovery/minuitwrp/events.cpp"

# Clean stale minuitwrp/recovery-root outputs. Incremental builds can otherwise
# retain an older libminuitwrp.so in the ramdisk even when source changed.
if [[ -n "${OUT_DIR:-}" ]]; then
  rm -rf "$OUT_DIR/target/product/tiro/recovery"
  rm -f "$OUT_DIR/target/product/tiro/system/lib64/libminuitwrp.so"
  rm -f "$OUT_DIR/target/product/tiro/recovery.img"
fi

"$ROOT/scripts/validate_tree.py"
