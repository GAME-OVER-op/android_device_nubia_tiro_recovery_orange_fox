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
fi
