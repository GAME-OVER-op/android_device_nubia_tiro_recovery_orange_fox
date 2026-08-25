#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FOX_SRC="${FOX_SRC:-$ROOT/.work/fox_12.1}"
export OUT_DIR="${OUT_DIR:-$ROOT/.work/out}"
export FOX_BUILD_DEVICE=tiro
export FOX_BUILD_TYPE="${FOX_BUILD_TYPE:-Unofficial}"
export TIRO_BUILD_VERSION="${TIRO_BUILD_VERSION:-local}"
export ALLOW_MISSING_DEPENDENCIES=true
export LC_ALL=C

if [[ ! -d "$FOX_SRC/.repo" ]]; then
  "$ROOT/scripts/sync_fox.sh"
fi

"$ROOT/scripts/prepare_source.sh"

cd "$FOX_SRC"
source build/envsetup.sh
lunch twrp_tiro-eng
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
mka -j"$BUILD_JOBS" adbd recoveryimage

PRODUCT_OUT="$OUT_DIR/target/product/tiro"
IMG="$PRODUCT_OUT/recovery.img"
[[ -f "$IMG" ]] || { echo "ERROR: recovery.img was not produced at $IMG" >&2; exit 1; }

rm -rf "$ROOT/dist"
mkdir -p "$ROOT/dist"
cp "$IMG" "$ROOT/dist/recovery.img"
"$ROOT/scripts/verify_recovery.sh" "$ROOT/dist/recovery.img" "$PRODUCT_OUT"
sha256sum "$ROOT/dist/recovery.img" > "$ROOT/dist/recovery.img.sha256"
"$ROOT/scripts/make_build_info.sh" "$ROOT/dist/recovery.img" "$ROOT/dist/build-info.txt" "$FOX_SRC"

echo
echo "Build complete:"
ls -lh "$ROOT/dist/"
