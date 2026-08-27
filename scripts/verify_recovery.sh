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
    if grep -aFq 'IVibrator/vibratorfeature' "$LIB"; then
      echo "ERROR: Xiaomi AIDL vibrator instance is still compiled into libminuitwrp.so" >&2
      exit 1
    fi
    if ! grep -aFq '/sys/class/timed_output/vibrator/cont' "$LIB"; then
      echo "ERROR: native Tiro/Awinic continuous haptics backend missing from libminuitwrp.so" >&2
      exit 1
    fi
    if ! grep -aFq 'TIRO: using firmware-independent Awinic continuous haptics' "$LIB"; then
      echo "ERROR: Tiro continuous haptics marker missing from libminuitwrp.so" >&2
      exit 1
    fi
    echo "Haptics check: native Awinic continuous backend present; Xiaomi blocking AIDL path absent"
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
  STYLES_XML="$PRODUCT_OUT/recovery/root/twres/resources/styles.xml"
  if [[ ! -f "$INSTALL_XML" ]]; then
    echo "ERROR: built install.xml not found" >&2
    exit 1
  fi
  NORMAL_STYLE_COUNT="$(grep -Fc '<button style="btn_raised_s">' "$INSTALL_XML" || true)"
  HILITE_STYLE_COUNT="$(grep -Fc '<button style="btn_raised_s_hl">' "$INSTALL_XML" || true)"
  if [[ "$NORMAL_STYLE_COUNT" != "4" || "$HILITE_STYLE_COUNT" != "2" ]]; then
    echo "ERROR: post-flash buttons do not use all six native compact styles" >&2
    echo "  normal=$NORMAL_STYLE_COUNT highlighted=$HILITE_STYLE_COUNT" >&2
    exit 1
  fi
  if grep -Eq '<image resource="btn_raised_s(_hl)?"/>' "$INSTALL_XML"; then
    echo "ERROR: post-flash buttons contain explicit child images; this hides labels on tiro" >&2
    exit 1
  fi
  [[ "$(grep -Fc '<text>{@tiro_wipe_dalvik_btn}</text>' "$INSTALL_XML" || true)" == "2" ]] || { echo "ERROR: Dalvik post-flash labels missing" >&2; exit 1; }
  [[ "$(grep -Fc 'tw_text1={@tiro_wipe_dalvik_confirm}' "$INSTALL_XML" || true)" == "2" ]] || { echo "ERROR: Dalvik confirmation strings missing" >&2; exit 1; }
  [[ "$(grep -Fc 'tw_action_text1={@tiro_wiping_dalvik}' "$INSTALL_XML" || true)" == "2" ]] || { echo "ERROR: Dalvik progress strings missing" >&2; exit 1; }
  [[ "$(grep -Fc 'tw_complete_text1={@tiro_wipe_dalvik_complete}' "$INSTALL_XML" || true)" == "2" ]] || { echo "ERROR: Dalvik completion strings missing" >&2; exit 1; }
  [[ "$(grep -Fc '<text>{@reboot_recovery_btn}</text>' "$INSTALL_XML" || true)" == "2" ]] || { echo "ERROR: reboot-recovery labels missing" >&2; exit 1; }
  [[ "$(grep -Fc '<text>{@reboot_system_btn}</text>' "$INSTALL_XML" || true)" == "2" ]] || { echo "ERROR: reboot-system labels missing" >&2; exit 1; }
  if grep -Fq 'tw_action_param=/cache' "$INSTALL_XML"; then
    echo "ERROR: post-flash UI still tries to wipe nonexistent /cache" >&2
    exit 1
  fi
  LANG_DIR="$PRODUCT_OUT/recovery/root/twres/languages"
  if [[ ! -d "$LANG_DIR" ]]; then
    echo "ERROR: built OrangeFox language directory missing" >&2
    exit 1
  fi
  python3 - "$LANG_DIR" <<'PY_LANG'
import re, sys
from pathlib import Path
root = Path(sys.argv[1])
keys = ("tiro_wipe_dalvik_btn", "tiro_wipe_dalvik_confirm", "tiro_wiping_dalvik", "tiro_wipe_dalvik_complete")
files = sorted(root.glob("*.xml"))
if not files:
    raise SystemExit("ERROR: no built OrangeFox language XML files")
for p in files:
    text = p.read_text(encoding="utf-8", errors="strict")
    for key in keys:
        if not re.search(rf'<string\s+name=["\']{re.escape(key)}["\']>', text):
            raise SystemExit(f"ERROR: {p.name} missing Tiro language key {key}")
print(f"Dalvik localization check: {len(files)} language files contain all Tiro keys")
PY_LANG
  if [[ ! -f "$IMAGES_XML" || ! -f "$STYLES_XML" ]]; then
    echo "ERROR: built OrangeFox theme registries missing" >&2
    exit 1
  fi
  python3 - "$STYLES_XML" "$IMAGES_XML" <<'PY_GUI'
import re, sys
from pathlib import Path
styles = Path(sys.argv[1]).read_text(encoding='utf-8', errors='strict')
images = Path(sys.argv[2]).read_text(encoding='utf-8', errors='strict')
for name, color in (("btn_raised_s", "%text%"), ("btn_raised_s_hl", "%text_hl_btn%")):
    if not re.search(rf"\bname\s*=\s*['\"]{name}['\"]", images):
        raise SystemExit(f"ERROR: {name} image/shape resource missing")
    m = re.search(rf"<style\s+name\s*=\s*['\"]{name}['\"]\s*>(.*?)</style>", styles, re.S)
    if not m:
        raise SystemExit(f"ERROR: {name} style missing")
    body = m.group(1)
    if not re.search(r"<font\b[^>]*\bresource\s*=\s*['\"]Secondary['\"]", body):
        raise SystemExit(f"ERROR: {name} style has no Secondary font")
    if color not in body:
        raise SystemExit(f"ERROR: {name} style has wrong/missing text color")
    if not re.search(rf"<image\b[^>]*\bresource\s*=\s*['\"]{name}['\"]", body):
        raise SystemExit(f"ERROR: {name} style does not reference its background resource")
PY_GUI
  echo "GUI check: six post-flash buttons use native style -> font/image -> shape chain"

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
