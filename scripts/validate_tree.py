#!/usr/bin/env python3
"""Static validation for the bundled tiro recovery device tree."""
from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "device/nubia/tiro"
errors: list[str] = []

required = [
    "BoardConfig.mk",
    "AndroidProducts.mk",
    "twrp_tiro.mk",
    "fox_tiro.mk",
    "prebuilt/kernel",
    "recovery/root/init.recovery.qcom.rc",
    "recovery/root/system/etc/recovery.fstab",
    "recovery/root/vendor/bin/prepdecrypt.sh",
    "recovery/root/vendor/bin/hw/android.hardware.security.keymint-service-qti",
    "recovery/root/vendor/bin/hw/android.hardware.gatekeeper-service-qti",
    "recovery/root/vendor/bin/qseecomd",
    "recovery/root/vendor/lib64/libqtikeymint.so",
    "recovery/root/vendor/lib64/libQSEEComAPI.so",
    "recovery/root/system/bin/tiro-haptics-debug.sh",
]
for rel in required:
    if not (D / rel).exists():
        errors.append(f"missing: {rel}")

for rel in [
    "config/source-lock.env",
    ".github/workflows/build-recovery.yml",
    "docs/CI.md",
    "reference/working-ramdisk.sha256",
    "reference/working-ramdisk-symlinks.txt",
    "reference/source-recovery-root.sha256",
    "reference/SPLIT_IMAGE_LAYOUT.txt",
    "reference/WORKING_DECRYPT_STACK.txt",
    "reference/KNOWN_GOOD_RUNTIME_PROFILE.txt",
    "scripts/setup_ci_swap.sh",
    "scripts/build_heartbeat.sh",
    "scripts/patch_theme_button_resources.py",
]:
    if not (ROOT / rel).is_file():
        errors.append(f"missing: {rel}")

board = (D / "BoardConfig.mk").read_text()
for forbidden in (
    "TW_NO_HAPTICS := true",
    "TW_SUPPORT_INPUT_AIDL_HAPTICS := true",
    'TW_SUPPORT_INPUT_AIDL_HAPTICS_FQNAME := "IVibrator/vibratorfeature"',
):
    if forbidden in board:
        errors.append(f"blocking/disabled-haptics flag present: {forbidden}")

# On-device probing and a direct evdev hardware test prove that Tiro's
# awinic_haptic device drives the actuator through FF_RUMBLE. It advertises
# FF_CONSTANT too, but that path is not reliable while haptic_ram.bin is absent.
haptic_patcher = (ROOT / "scripts/patch_haptics.py").read_text()
rumble_probe = haptic_patcher.find("tiro_ff_test_bit(FF_RUMBLE, ff_bits)")
constant_probe = haptic_patcher.find("tiro_ff_test_bit(FF_CONSTANT, ff_bits)")
if "TIRO_INPUT_FF_HAPTICS_V2" not in haptic_patcher:
    errors.append("Tiro FF_RUMBLE-first haptics backend missing")
if "/sys/class/timed_output/vibrator/cont" in haptic_patcher:
    errors.append("stale nonexistent Tiro timed_output/cont haptics backend remains")
if rumble_probe < 0 or constant_probe < 0 or rumble_probe > constant_probe:
    errors.append("Tiro input haptics must prefer FF_RUMBLE over FF_CONSTANT")
if "effect.id = static_cast<__s16>(tiro_ff_effect_id);" not in haptic_patcher:
    errors.append("input-FF backend does not reuse its persistent effect slot")
if "tiro_stop_ff_effect(fd);" not in haptic_patcher:
    errors.append("input-FF backend does not stop an in-flight effect before retrigger")

checks = {
    "BOARD_BOOT_HEADER_VERSION": "4",
    "BOARD_KERNEL_PAGESIZE": "4096",
    "BOARD_RECOVERYIMAGE_PARTITION_SIZE": "104857600",
    "BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE": "true",
    "BOARD_RAMDISK_USE_LZ4": "true",
    "BOARD_SUPER_PARTITION_SIZE": "11811160064",
    "BOARD_QTI_DYNAMIC_PARTITIONS_SIZE": "11809841488",
}
for key, value in checks.items():
    if key not in board or value not in board:
        errors.append(f"expected {key}={value}")

# Runtime fixes validated from the 2026-10-02 on-device logs.
recovery_root = D / "recovery/root"
usb_rc = (recovery_root / "init.recovery.usb.rc").read_text()
qcom_rc = (recovery_root / "init.recovery.qcom.rc").read_text()
ueventd_rc = (recovery_root / "vendor/etc/ueventd.rc").read_text()
recovery_fstab = (recovery_root / "system/etc/recovery.fstab").read_text()
install_xml = (recovery_root / "twres/pages/install.xml").read_text()

# Plain ADB is already handled by the base recovery init.  The device-specific
# USB rc must not race it by linking ffs.adb/binding g1/UDC a second time.
if "wait /sys/class/udc/${ro.boot.usbcontroller} 5" not in usb_rc:
    errors.append("USB init must wait up to 5 seconds for the Tiro UDC")
if "setprop sys.usb.config adb" not in usb_rc:
    errors.append("USB init must request adb only after the UDC wait")
if "/config/usb_gadget/g2" in usb_rc:
    errors.append("stale unused USB gadget g2 setup remains")
if "on property:sys.usb.config=adb && property:sys.usb.configfs=1" in usb_rc:
    errors.append("device USB rc duplicates the base recovery plain-ADB start action")
if "on property:sys.usb.ffs.ready=1 && property:sys.usb.config=adb && property:sys.usb.configfs=1" in usb_rc:
    errors.append("device USB rc duplicates the base recovery plain-ADB gadget bind action")
if "on boot\n    setprop sys.usb.config adb" in qcom_rc:
    errors.append("qcom rc still requests adb before the UDC is ready")

# Gatekeeper depends on the QSEE listener stack. It must be started only after
# qseecomd publishes vendor.sys.listeners.registered=true, alongside KeyMint.
listener_at = qcom_rc.find("on property:vendor.sys.listeners.registered=true")
gatekeeper_at = qcom_rc.find("start vendor.gatekeeper_default")
if gatekeeper_at < 0:
    errors.append("Gatekeeper recovery start is missing")
elif listener_at < 0 or gatekeeper_at < listener_at:
    errors.append("Gatekeeper is started before QSEE listeners are ready")
if qcom_rc.count("start vendor.gatekeeper_default") != 1:
    errors.append("Gatekeeper must have exactly one explicit recovery start")
if "write /sys/class/remoteproc/remoteproc0/state start" in qcom_rc:
    errors.append("SPSS remoteproc0 forced start still present in bundled device tree")

# ueventd rejects malformed /sys rules.  Keep every /sys rule in the modern
# nodename/attribute/mode/uid/gid form and do not import a file we do not ship.
if "import /vendor/etc/ueventd.qcom.userdebug.rc" in ueventd_rc:
    errors.append("vendor ueventd still imports missing ueventd.qcom.userdebug.rc")
if "subsystem dma_heap" in ueventd_rc:
    errors.append("vendor ueventd duplicates the base dma_heap subsystem")
for lineno, line in enumerate(ueventd_rc.splitlines(), 1):
    stripped = line.strip()
    if stripped == "*/":
        errors.append(f"vendor ueventd contains stray invalid token at line {lineno}")
    if stripped.startswith("/sys/") and len(stripped.split()) not in (5, 6):
        errors.append(f"vendor ueventd malformed /sys rule at line {lineno}: {stripped}")

# NX769J has no Xiaomi mi_ext logical partition; probing it only produces a
# deterministic startup error. The install page must use OrangeFox's existing
# localized forced-encryption label instead of the private/missing auto_dfe_chk.
if any(line.lstrip().startswith("mi_ext ") for line in recovery_fstab.splitlines()):
    errors.append("stale Xiaomi mi_ext entries remain in recovery.fstab")
if "auto_dfe_chk" in install_xml:
    errors.append("install.xml still references missing auto_dfe_chk string")
if "{@fox_forced_encryption_chk}" not in install_xml:
    errors.append("install.xml does not use OrangeFox fox_forced_encryption_chk resource")

# AOSP/OrangeFox envsetup is intentionally interactive-shell oriented: it is
# not nounset-safe and can return 1 from a harmless final optional probe. CI and
# local builds must therefore disable -u for Android shell functions and disable
# -e only around the source command, then restore -e and validate the environment.
workflow = (ROOT / ".github/workflows/build-recovery.yml").read_text()
local_build = (ROOT / "scripts/build_local.sh").read_text()
for label, text in (("GitHub workflow", workflow), ("local build script", local_build)):
    source_at = text.find("source build/envsetup.sh")
    if source_at < 0:
        errors.append(f"{label}: missing build/envsetup.sh source")
        continue
    prior = text[max(0, source_at - 1200):source_at]
    after = text[source_at:source_at + 1800]
    if "set +u" not in prior:
        errors.append(f"{label}: must disable bash nounset before envsetup.sh")
    if "set +e" not in prior:
        errors.append(f"{label}: must temporarily disable bash errexit before envsetup.sh")
    if "ENVSETUP_RC=$?" not in after:
        errors.append(f"{label}: must capture envsetup return code")
    if "set -e" not in after:
        errors.append(f"{label}: must restore bash errexit after envsetup.sh")
    if "declare -F lunch" not in after or "declare -F mka" not in after:
        errors.append(f"{label}: must validate lunch/mka after envsetup.sh")
    if "RESOLVED_TOP=" not in after or "gettop" not in after:
        errors.append(f"{label}: must validate Android top after envsetup.sh")


# OrangeFox accepts FOX_MAINTAINER_PATCH_VERSION only as a canonical
# decimal whole number. CI must never feed a Git SHA into this field.
if 'uses: actions/checkout@v6' not in workflow:
    errors.append("GitHub workflow must use actions/checkout@v6 (Node.js 24 runtime)")
if 'uses: actions/upload-artifact@v6' not in workflow:
    errors.append("GitHub workflow must use actions/upload-artifact@v6 (Node.js 24 runtime)")
if 'scripts/setup_ci_swap.sh 16 18' not in workflow:
    errors.append("GitHub workflow must request 16 GiB CI swap with disk reserve")
if 'setsid "$GITHUB_WORKSPACE/scripts/build_heartbeat.sh" 60 &' not in workflow:
    errors.append("GitHub workflow must start the 60-second heartbeat in its own process group")
if 'trap cleanup_build_monitor EXIT INT TERM' not in workflow:
    errors.append("GitHub workflow must clean up only the build heartbeat with a trap")
if 'sudo swapoff /swapfile' in workflow:
    errors.append("GitHub workflow must not swapoff CI swap after compilation; it can hang the hosted runner")

swap_helper = (ROOT / "scripts/setup_ci_swap.sh").read_text()
if "/swapfile-ci-extra" not in swap_helper:
    errors.append("CI swap helper must add missing swap capacity via /swapfile-ci-extra")
if "current_swap_bytes" not in swap_helper or "DESIRED_TOTAL_GIB" not in swap_helper:
    errors.append("CI swap helper must target total active swap, including any runner-provided swap")
if "vm.swappiness=60" not in swap_helper:
    errors.append("CI swap helper must use the validated swappiness=60 setting")
if 'leaving CI swap enabled until runner teardown' not in workflow:
    errors.append("GitHub workflow must document that swap stays active until ephemeral runner teardown")
if 'export TIRO_BUILD_VERSION="${GITHUB_RUN_NUMBER}"' not in workflow:
    errors.append("GitHub workflow must use numeric GITHUB_RUN_NUMBER for TIRO_BUILD_VERSION")
if 'export TIRO_BUILD_VERSION="${GITHUB_SHA::8}"' in workflow:
    errors.append("GitHub workflow must not use hexadecimal Git SHA as OrangeFox patch version")
if 'export TIRO_BUILD_VERSION="${TIRO_BUILD_VERSION:-0}"' not in local_build:
    errors.append("local build must default TIRO_BUILD_VERSION to numeric 0")
# Keep the temporary GUIButton diagnostic patch until the offending theme
# elements have been identified on-device.  It must be applied during source
# preparation and CI must verify the marker in the patched OrangeFox source.
gui_patch = ROOT / "scripts/patch_gui_button_logging.py"
prepare_source = (ROOT / "scripts/prepare_source.sh").read_text()
if not gui_patch.is_file():
    errors.append("GUI button diagnostic patch script is missing")
else:
    gui_patch_text = gui_patch.read_text()
    if "TIRO_GUI_BUTTON_DIAGNOSTICS" not in gui_patch_text:
        errors.append("GUI button diagnostic patch marker is missing")
    if "style='%s'" not in gui_patch_text or "action='%s'" not in gui_patch_text:
        errors.append("GUI button diagnostics must report style and first action")
if "patch_gui_button_logging.py" not in prepare_source:
    errors.append("prepare_source.sh does not apply GUI button diagnostics")
if 'grep -n "TIRO_GUI_BUTTON_DIAGNOSTICS"' not in workflow:
    errors.append("GitHub workflow does not verify GUI button diagnostics")

theme_patch = ROOT / "scripts/patch_theme_button_resources.py"
if not theme_patch.is_file():
    errors.append("OrangeFox compact-button resource patcher is missing")
else:
    theme_patch_text = theme_patch.read_text()
    for expected in ("btn_raised_s", "btn_raised_s_hl", "TIRO_POSTFLASH_BUTTON_SHAPES", "TIRO_POSTFLASH_BUTTON_STYLES"):
        if expected not in theme_patch_text:
            errors.append(f"theme resource patcher missing marker/resource: {expected}")
if "patch_theme_button_resources.py" not in prepare_source:
    errors.append("prepare_source.sh does not ensure compact post-flash button resources")
if "patch_dalvik_language_resources.py" not in prepare_source:
    errors.append("prepare_source.sh does not install Tiro Dalvik-only localization resources")

unused_patch = ROOT / "scripts/patch_unused_recovery_services.py"
if not unused_patch.is_file():
    errors.append("minimal unused-service recovery patcher is missing")
else:
    unused_text = unused_patch.read_text()
    for marker in ("se_omapi", "vendor.secure_element", "vendor.keymint-strongbox", "remoteproc0", "boot_adsp"):
        if marker not in unused_text:
            errors.append(f"unused-service patcher missing required marker: {marker}")
if "patch_unused_recovery_services.py" not in prepare_source:
    errors.append("prepare_source.sh does not disable proven-broken recovery-only services")
if 'patch_theme_button_resources.py" --check "$FOX_SRC"' not in workflow:
    errors.append("GitHub workflow does not verify patched OrangeFox button resources")

# Final Red Magic cleanup. Keep the post-flash buttons in the native OrangeFox
# form: their style supplies BOTH font/text properties and the image resource.
# A previous workaround added a child <image> to each button; that made the
# background visible but covered/suppressed the labels on-device. Source prep
# now repairs the style -> image -> shape chain instead.
install_xml = (D / "recovery/root/twres/pages/install.xml").read_text()
if install_xml.count('<button style="btn_raised_s">') != 4:
    errors.append("install.xml must contain four native btn_raised_s post-flash buttons")
if install_xml.count('<button style="btn_raised_s_hl">') != 2:
    errors.append("install.xml must contain two native btn_raised_s_hl post-flash buttons")
if '<image resource="btn_raised_s"/>' in install_xml or '<image resource="btn_raised_s_hl"/>' in install_xml:
    errors.append("post-flash buttons must not contain explicit child images; background comes from style")
if install_xml.count('<text>{@tiro_wipe_dalvik_btn}</text>') != 2:
    errors.append("both post-flash pages must contain the localized Dalvik button label")
for token in ('tw_text1={@tiro_wipe_dalvik_confirm}', 'tw_action_text1={@tiro_wiping_dalvik}', 'tw_complete_text1={@tiro_wipe_dalvik_complete}'):
    if install_xml.count(token) != 2:
        errors.append(f"both post-flash pages must contain localized Dalvik action token: {token}")
if install_xml.count('<text>{@reboot_recovery_btn}</text>') != 2:
    errors.append("both post-flash pages must contain the reboot-recovery label")
if install_xml.count('<text>{@reboot_system_btn}</text>') != 2:
    errors.append("both post-flash pages must contain the reboot-system label")
if 'tw_action_param=/cache' in install_xml:
    errors.append("A/B post-flash page must not try to wipe the nonexistent /cache partition")
if install_xml.count('tw_action_param=dalvik') < 2:
    errors.append("both post-flash completion pages must offer a Dalvik wipe")

# Red Magic has no Xiaomi-style rescue-as-cache partition. Without a /cache
# partition OrangeFox get_log_dir() falls back to /data, which is the correct
# persistent log location on this decrypted A/B device.
for rel in ("recovery/root/system/etc/recovery.fstab", "recovery/root/system/etc/twrp.flags"):
    text = (D / rel).read_text()
    if '/cache' in text or 'by-name/rescue' in text:
        errors.append(f"stale Xiaomi cache/rescue mapping remains in {rel}")

# Prove that recovery.fstab differs from the known-good working file only by
# removal of the invalid rescue -> /cache row and the stale Xiaomi mi_ext rows;
# all FBE/decrypt mount data stays byte-for-byte identical after normalisation.
ref_fstab = ROOT / "reference/KNOWN_GOOD_RECOVERY_FSTAB.txt"
if not ref_fstab.is_file():
    errors.append("missing reference/KNOWN_GOOD_RECOVERY_FSTAB.txt")
else:
    def without_tiro_invalid_rows(text: str) -> str:
        return "\n".join(
            ln for ln in text.splitlines()
            if not ('/cache' in ln and 'by-name/rescue' in ln)
            and not ln.lstrip().startswith('mi_ext ')
        ).strip()
    current = (D / "recovery/root/system/etc/recovery.fstab").read_text()
    if without_tiro_invalid_rows(ref_fstab.read_text()) != current.strip():
        errors.append("recovery.fstab changed beyond the intentional cache/mi_ext cleanup")

# These three Xiaomi modules produced Exec format error on the Red Magic kernel.
# Native Goodix/input and Awinic FF haptics are already confirmed working.
forbidden_modules = ("nt38771_touch", "si_haptic", "xiaomi_touch")
runatboot = (D / "recovery/root/system/bin/runatboot.sh").read_text()
for mod in forbidden_modules:
    if mod in runatboot or f"{mod}.ko" in board:
        errors.append(f"incompatible Xiaomi module is still requested: {mod}")
    if (D / "recovery/root/vendor/lib/modules/1.1" / f"{mod}.ko").exists():
        errors.append(f"incompatible Xiaomi module is still bundled: {mod}.ko")

vendorsetup = (D / "vendorsetup.sh").read_text()
if 'export FOX_MAINTAINER_PATCH_VERSION="$TIRO_PATCH_VERSION"' not in vendorsetup:
    errors.append("vendorsetup must export normalized numeric FOX_MAINTAINER_PATCH_VERSION")
if 'export FOX_ENABLE_APP_MANAGER=1' not in vendorsetup:
    errors.append("OrangeFox App Manager must be explicitly enabled")
if 'FOX_DISABLE_APP_MANAGER=1' in vendorsetup or 'export FOX_DISABLE_APP_MANAGER=1' in vendorsetup:
    errors.append("OrangeFox App Manager is explicitly disabled")
for root_flag in (
    'export FOX_ENABLE_KERNELSU_SUPPORT=1',
    'export FOX_ENABLE_KERNELSU_NEXT_SUPPORT=1',
    'export FOX_ENABLE_SUKISU_SUPPORT=1',
):
    if root_flag not in vendorsetup:
        errors.append(f"root-module compatibility flag missing: {root_flag}")
if 'TIRO_BUILD_VERSION:-local' in vendorsetup or 'FOX_MAINTAINER_PATCH_VERSION="${TIRO_BUILD_VERSION:-local}"' in vendorsetup:
    errors.append("vendorsetup contains non-numeric local patch-version fallback")

# The known-good reference recovery was built on the Android 14 / SDK 34
# OrangeFox line. Its ramdisk explicitly reports ro.build.version.sdk=34,
# ro.product.first_api_level=34 and ro.board.first_api_level=34. Building this
# tree against fox_12.1/SDK 32 can compile after forcing API values down, but
# produces an incompatible userspace which can stall at the OrangeFox splash.
device_mk = (D / "device.mk").read_text()
for expected in (
    "PRODUCT_SHIPPING_API_LEVEL  := 34",
    "PRODUCT_TARGET_VNDK_VERSION := 34",
    "BOARD_SHIPPING_API_LEVEL    := 34",
    "SHIPPING_API_LEVEL          := 34",
):
    if expected not in device_mk:
        errors.append(f"fox_14.1/API34 compatibility setting missing: {expected}")

lock = (ROOT / "config/source-lock.env").read_text()
if "FOX_BRANCH=14.1" not in lock:
    errors.append("source lock must use OrangeFox fox_14.1")
if "FOX_BRANCH=12.1" in lock:
    errors.append("fox_12.1 is incompatible with the known-good SDK34 recovery profile")

for label, text in (("GitHub workflow", workflow), ("local build script", local_build)):
    if "fox_12.1" in text:
        errors.append(f"{label}: stale fox_12.1 source path remains")
    if "twrp_tiro-eng" in text and "twrp_tiro-ap2a-eng" not in text:
        errors.append(f"{label}: fox_14.1 build must use twrp_tiro-ap2a-eng")


product = (D / "twrp_tiro.mk").read_text()
for expected in (
    "PRODUCT_DEVICE := tiro",
    "PRODUCT_MODEL := NX769J",
    "PRODUCT_MANUFACTURER := nubia",
):
    if expected not in product:
        errors.append(f"missing product identity: {expected}")

rc_path = D / "recovery/root/vendor/etc/init/vendor.xiaomi.hardware.vibratorfeature.service.rc"
if rc_path.is_file():
    rc = rc_path.read_text()
    if "on init\n    start vibratorfeature-hal-service" in rc:
        errors.append("Xiaomi vibratorfeature service is still auto-started")

# Verify that the binary/script portion of the decryption chain preserved from
# the known-good ramdisk still matches byte-for-byte. init.recovery.qcom.rc is
# intentionally excluded: only its proven-bad service ordering was corrected and
# the semantic assertions above protect the QSEE/Gatekeeper/ADSP requirements.
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

manifest_path = ROOT / "reference/working-ramdisk.sha256"
working_hashes: dict[str, str] = {}
if manifest_path.is_file():
    for line in manifest_path.read_text(errors="replace").splitlines():
        if "  " not in line:
            continue
        digest, rel = line.split("  ", 1)
        rel = rel.removeprefix("./")
        working_hashes[rel] = digest

critical_decrypt = [
    "vendor/bin/hw/android.hardware.security.keymint-service-qti",
    "vendor/bin/hw/android.hardware.gatekeeper-service-qti",
    "vendor/bin/qseecomd",
    "vendor/lib64/libqtikeymint.so",
    "vendor/lib64/libQSEEComAPI.so",
    "vendor/bin/prepdecrypt.sh",
]
for rel in critical_decrypt:
    src = D / "recovery/root" / rel
    expected = working_hashes.get(rel)
    if not expected:
        errors.append(f"known-good ramdisk hash missing for: {rel}")
    elif src.is_file() and sha256(src) != expected:
        errors.append(f"known-good decrypt file changed: {rel}")

if errors:
    print("Tree validation FAILED:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print("Tree validation OK")
print("  target: nubia tiro / NX769J")
print("  recovery partition: 100 MiB")
print("  header: v4")
print("  ramdisk: LZ4")
print("  embedded kernel: excluded")
print("  haptics: hardware-verified Awinic FF_RUMBLE, persistent input-FF backend")
print("  source profile: OrangeFox fox_14.1 / Android 14 / SDK 34")
print("  CI memory: 16 GiB total active swap target + 60 s heartbeat; preserves existing runner swap; no post-build swapoff")
print("  GitHub JS actions: checkout@v6 + upload-artifact@v6 / Node.js 24")
print("  decrypt compatibility stack: critical binaries byte-identical; qcom init ordering fixed; fstab differs only by invalid cache/mi_ext removal")
print("  OrangeFox App Manager: enabled")
print("  GUI post-flash buttons: native styled backgrounds + visible text path; diagnostics retained")
print("  cache handling: no fake rescue/cache partition; OrangeFox persistent logs fall back to /data")
print("  startup modules: incompatible Xiaomi touch/haptic modules removed")
print("  root modules: OrangeFox fox_14.1 built-in manager; Magisk/APatch/KernelSU family")
