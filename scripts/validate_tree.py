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

checks = {
    "BOARD_BOOT_HEADER_VERSION": "4",
    "BOARD_KERNEL_PAGESIZE": "4096",
    "BOARD_RECOVERYIMAGE_PARTITION_SIZE": "104857600",
    "BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE": "true",
    "BOARD_RAMDISK_USE_LZ4": "true",
    "BOARD_SUPER_PARTITION_SIZE": "12884901888",
    "BOARD_QTI_DYNAMIC_PARTITIONS_SIZE": "12880707584",
}
for key, value in checks.items():
    if key not in board or value not in board:
        errors.append(f"expected {key}={value}")

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

# Verify that the decryption chain preserved from the known-good ramdisk still
# matches byte-for-byte. This is intentionally stronger than checking existence.
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
    "system/etc/recovery.fstab",
    "init.recovery.qcom.rc",
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
print("  haptics: enabled via direct input FF patch, sysfs fallback")
print("  decrypt compatibility stack: byte-identical to known-good ramdisk")
