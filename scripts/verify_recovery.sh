#!/usr/bin/env bash
set -euo pipefail

IMG="${1:?Usage: verify_recovery.sh <recovery.img> [product-out]}"
PRODUCT_OUT="${2:-}"
MAX=104857600

[[ -f "$IMG" ]] || { echo "ERROR: image not found: $IMG" >&2; exit 2; }
SIZE="$(stat -c '%s' "$IMG")"
MAGIC="$(dd if="$IMG" bs=1 count=8 status=none)"

[[ "$MAGIC" == "ANDROID!" ]] || { echo "ERROR: Android boot image magic missing" >&2; exit 1; }
(( SIZE <= MAX )) || { echo "ERROR: image is larger than the 100 MiB recovery partition ($SIZE > $MAX)" >&2; exit 1; }

printf 'recovery.img size: %s bytes\n' "$SIZE"
sha256sum "$IMG"

if command -v avbtool >/dev/null 2>&1; then
  echo
  echo "AVB information:"
  avbtool info_image --image "$IMG" || true
fi

if [[ -n "$PRODUCT_OUT" ]]; then
  LIB="$PRODUCT_OUT/recovery/root/system/lib64/libminuitwrp.so"
  if [[ ! -f "$LIB" ]]; then
    LIB="$PRODUCT_OUT/system/lib64/libminuitwrp.so"
  fi
  if [[ -f "$LIB" ]]; then
    if strings "$LIB" | grep -Fq 'IVibrator/vibratorfeature'; then
      echo "ERROR: Xiaomi AIDL vibrator instance is still compiled into libminuitwrp.so" >&2
      exit 1
    fi
    echo "Haptics check: no Xiaomi vibratorfeature instance in libminuitwrp.so"
  else
    echo "WARNING: libminuitwrp.so was not found for binary inspection" >&2
  fi

  for f in \
    recovery/root/vendor/bin/hw/android.hardware.security.keymint-service-qti \
    recovery/root/vendor/bin/hw/android.hardware.gatekeeper-service-qti \
    recovery/root/vendor/bin/prepdecrypt.sh \
    recovery/root/vendor/lib64/libqtikeymint.so; do
    [[ -e "$PRODUCT_OUT/$f" ]] || { echo "ERROR: missing build output: $f" >&2; exit 1; }
  done
  echo "Decrypt stack check: required compatibility files are present"

  PROP="$PRODUCT_OUT/recovery/root/default.prop"
  [[ -f "$PROP" ]] || PROP="$PRODUCT_OUT/recovery/root/prop.default"
  if [[ ! -f "$PROP" ]]; then
    echo "ERROR: built recovery default properties not found" >&2
    exit 1
  fi

  prop_value() {
    sed -n "s/^$1=//p" "$PROP" | tail -n1
  }
  SDK="$(prop_value ro.build.version.sdk)"
  FIRST_API="$(prop_value ro.product.first_api_level)"
  BOARD_FIRST_API="$(prop_value ro.board.first_api_level)"
  if [[ "$SDK" != "34" || "$FIRST_API" != "34" || "$BOARD_FIRST_API" != "34" ]]; then
    echo "ERROR: built ramdisk does not match known-good Android 14/API34 profile" >&2
    echo "  ro.build.version.sdk=$SDK" >&2
    echo "  ro.product.first_api_level=$FIRST_API" >&2
    echo "  ro.board.first_api_level=$BOARD_FIRST_API" >&2
    exit 1
  fi
  echo "Runtime profile check: SDK 34 / first API 34 / board first API 34"

  INSTALL_XML="$PRODUCT_OUT/recovery/root/twres/pages/install.xml"
  IMAGES_XML="$PRODUCT_OUT/recovery/root/twres/resources/images.xml"
  if [[ ! -f "$INSTALL_XML" ]]; then
    echo "ERROR: built install.xml not found" >&2
    exit 1
  fi
  NORMAL_BG_COUNT="$(grep -Fc '<image resource="btn_raised_s"/>' "$INSTALL_XML" || true)"
  HILITE_BG_COUNT="$(grep -Fc '<image resource="btn_raised_s_hl"/>' "$INSTALL_XML" || true)"
  if [[ "$NORMAL_BG_COUNT" != "4" || "$HILITE_BG_COUNT" != "2" ]]; then
    echo "ERROR: post-flash buttons do not have all six explicit backgrounds" >&2
    echo "  normal=$NORMAL_BG_COUNT highlighted=$HILITE_BG_COUNT" >&2
    exit 1
  fi
  if grep -Fq 'tw_action_param=/cache' "$INSTALL_XML"; then
    echo "ERROR: post-flash UI still tries to wipe nonexistent /cache" >&2
    exit 1
  fi
  if [[ -f "$IMAGES_XML" ]]; then
    grep -Fq 'shape name="btn_raised_s"' "$IMAGES_XML" || { echo "ERROR: btn_raised_s resource missing" >&2; exit 1; }
    grep -Fq 'shape name="btn_raised_s_hl"' "$IMAGES_XML" || { echo "ERROR: btn_raised_s_hl resource missing" >&2; exit 1; }
  else
    echo "WARNING: built theme resource registry not found for shape verification" >&2
  fi
  echo "GUI check: six post-flash buttons have explicit visible backgrounds"

  RECOVERY_FSTAB="$PRODUCT_OUT/recovery/root/system/etc/recovery.fstab"
  TWRP_FLAGS="$PRODUCT_OUT/recovery/root/system/etc/twrp.flags"
  for f in "$RECOVERY_FSTAB" "$TWRP_FLAGS"; do
    if [[ -f "$f" ]] && grep -Eq '/cache|by-name/rescue' "$f"; then
      echo "ERROR: stale rescue/cache mapping survived into built ramdisk: $f" >&2
      exit 1
    fi
  done
  echo "Cache check: no fake rescue/cache partition; logs can fall back to /data"

  RUNATBOOT="$PRODUCT_OUT/recovery/root/system/bin/runatboot.sh"
  if [[ -f "$RUNATBOOT" ]] && grep -Eq 'nt38771_touch|si_haptic|xiaomi_touch' "$RUNATBOOT"; then
    echo "ERROR: incompatible Xiaomi modules survived into runatboot.sh" >&2
    exit 1
  fi
  for mod in nt38771_touch.ko si_haptic.ko xiaomi_touch.ko; do
    [[ ! -e "$PRODUCT_OUT/recovery/root/vendor/lib/modules/1.1/$mod" ]] || { echo "ERROR: incompatible module still bundled: $mod" >&2; exit 1; }
  done
  echo "Module check: incompatible Xiaomi touch/haptic modules removed"
fi
