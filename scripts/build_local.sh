#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FOX_SRC="${FOX_SRC:-$ROOT/.work/fox_14.1}"
export OUT_DIR="${OUT_DIR:-$ROOT/.work/out}"
export FOX_BUILD_DEVICE=tiro
export FOX_BUILD_TYPE="${FOX_BUILD_TYPE:-Unofficial}"
export TIRO_BUILD_VERSION="${TIRO_BUILD_VERSION:-0}"
export ALLOW_MISSING_DEPENDENCIES=true
export LC_ALL=C

if [[ ! -d "$FOX_SRC/.repo" ]]; then
  "$ROOT/scripts/sync_fox.sh"
fi

"$ROOT/scripts/prepare_source.sh"

cd "$FOX_SRC"
# AOSP/OrangeFox envsetup is intended for an interactive shell. It is not
# nounset-safe and its final optional probe can legitimately return 1. Keep
# nounset disabled for the Android build functions and disable errexit only for
# the source operation itself; then validate that envsetup actually succeeded.
set +u
set +e
source build/envsetup.sh
ENVSETUP_RC=$?
set -e

if ! declare -F lunch >/dev/null; then
  echo "ERROR: envsetup did not define lunch (rc=$ENVSETUP_RC)" >&2
  exit 1
fi
if ! declare -F mka >/dev/null; then
  echo "ERROR: envsetup did not define mka (rc=$ENVSETUP_RC)" >&2
  exit 1
fi
RESOLVED_TOP="$(gettop 2>/dev/null || true)"
if [[ "$RESOLVED_TOP" != "$FOX_SRC" ]]; then
  echo "ERROR: envsetup resolved Android top incorrectly" >&2
  echo "  expected: $FOX_SRC" >&2
  echo "  resolved: $RESOLVED_TOP" >&2
  exit 1
fi
if (( ENVSETUP_RC != 0 )); then
  echo "WARNING: build/envsetup.sh returned $ENVSETUP_RC after completing setup; continuing because lunch/mka/gettop validation passed." >&2
fi

lunch twrp_tiro-ap2a-eng

PLATFORM_SDK="$(get_build_var PLATFORM_SDK_VERSION)"
PRODUCT_API="$(get_build_var PRODUCT_SHIPPING_API_LEVEL)"
if [[ "$PLATFORM_SDK" != "34" || "$PRODUCT_API" != "34" ]]; then
  echo "ERROR: wrong OrangeFox runtime profile: platform_sdk=$PLATFORM_SDK product_api=$PRODUCT_API; expected 34/34" >&2
  exit 1
fi
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
