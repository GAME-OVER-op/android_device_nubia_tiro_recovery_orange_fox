#!/usr/bin/env python3
"""Disable only Tiro recovery services that are proven broken and unnecessary.

This patch is intentionally narrow and is applied only to the copied device tree
inside the OrangeFox source workspace.  The known-good bundled decrypt reference
remains untouched.

Disabled in recovery only:
  * se_omapi + QTI Secure Element AIDL: eSE hardware is not present/usable and the
    service exits with "Unknown eSE HW", causing a restart/poll loop.
  * NXP StrongBox KeyMint: never registers on Tiro recovery while default QTI
    KeyMint and NXP Weaver work; advertising it makes keystore2 retry forever.
  * explicit remoteproc0 start: on Tiro remoteproc0 is SPSS, not ADSP, and it
    always fails because spss.mdt is absent.  The separate boot_adsp path remains.

No binaries, libraries, modules, firmware, health services, touch, storage,
KeyMint default, Gatekeeper, Weaver, QSEE, or haptics are removed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

SE_OMAPI_RC = """# TIRO_RECOVERY_UNUSED_SERVICE_DISABLE\n# OMAPI/eSE is not used by OrangeFox on NX769J.  Do not auto-start or expose a\n# lazy interface: QTI Secure Element exits with \"Unknown eSE HW\" on this device.\nservice se_omapi /system/bin/se_omapi\n    class hal\n    disabled\n    user root\n    group root\n    seclabel u:r:recovery:s0\n"""


def ensure_disabled_service(path: Path, marker: str, service_name: str, remove_interfaces: bool = False) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing service rc: {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []
    in_target = False
    added_disabled = False
    marker_present = marker in text

    for line in lines:
        stripped = line.strip()
        if line.startswith("service "):
            if in_target and not added_disabled:
                out.append("    disabled")
            in_target = line.startswith(f"service {service_name} ")
            added_disabled = False
            out.append(line)
            continue
        if in_target:
            if stripped == "disabled":
                added_disabled = True
                out.append(line)
                continue
            if remove_interfaces and stripped.startswith("interface "):
                continue
        out.append(line)

    if in_target and not added_disabled:
        # Insert disabled immediately after the service declaration for clarity.
        for i in range(len(out) - 1, -1, -1):
            if out[i].startswith(f"service {service_name} "):
                out.insert(i + 1, "    disabled")
                break
    if not any(line.startswith(f"service {service_name} ") for line in out):
        raise RuntimeError(f"service {service_name!r} not found in {path}")
    if not marker_present:
        out.insert(0, f"# {marker}")
        out.insert(1, "# Disabled only in Tiro recovery; binaries are intentionally retained.")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def patch(root: Path) -> None:
    if not root.is_dir():
        raise RuntimeError(f"device tree root not found: {root}")

    # 1) Override OrangeFox's generic OMAPI startup in the device ramdisk overlay.
    se_omapi = root / "system/etc/init/se_omapi.rc"
    se_omapi.parent.mkdir(parents=True, exist_ok=True)
    se_omapi.write_text(SE_OMAPI_RC, encoding="utf-8")

    # 2) Keep the QTI Secure Element files, but never auto-start the known-broken HAL.
    se_rc = root / "vendor/etc/init/android.hardware.secure_element-service.qti.rc"
    ensure_disabled_service(
        se_rc,
        "TIRO_RECOVERY_UNUSED_SERVICE_DISABLE",
        "vendor.secure_element",
        remove_interfaces=True,
    )

    # 3) StrongBox NXP is not a working recovery path on Tiro.  Keep binaries/libs,
    #    but stop advertising the interface so keystore2 does not poll it forever.
    sb_rc = root / "vendor/etc/init/android.hardware.security.keymint-service.strongbox-nxp.rc"
    ensure_disabled_service(
        sb_rc,
        "TIRO_RECOVERY_UNUSED_SERVICE_DISABLE",
        "vendor.keymint-strongbox",
        remove_interfaces=True,
    )
    sb_manifest = root / "vendor/etc/vintf/manifest/android.hardware.security.keymint3-service.strongbox-nxp.xml"
    # Do not advertise a StrongBox instance that cannot start. Keep the binary and
    # libraries in the ramdisk; only the recovery VINTF declaration is removed.
    if sb_manifest.exists():
        sb_manifest.unlink()

    # 4) The known-good Xiaomi-derived rc assumes remoteproc0 is ADSP.  On Tiro it
    #    is explicitly remoteproc-spss.  Do not start it; preserve boot_adsp below.
    qcom_rc = root / "init.recovery.qcom.rc"
    text = qcom_rc.read_text(encoding="utf-8")
    bad = "    write /sys/class/remoteproc/remoteproc0/state start"
    replacement = (
        "    # TIRO_RECOVERY_UNUSED_SERVICE_DISABLE: remoteproc0 is SPSS on NX769J; "
        "spss.mdt is absent and SPSS is not required by OrangeFox."
    )
    if bad in text:
        text = text.replace(bad, replacement, 1)
    elif replacement not in text:
        raise RuntimeError("expected remoteproc0 start line not found in init.recovery.qcom.rc")
    if "    write /sys/kernel/boot_adsp/boot 1" not in text:
        raise RuntimeError("ADSP boot path unexpectedly missing; refusing to patch")
    qcom_rc.write_text(text, encoding="utf-8")

    print("Applied minimal Tiro recovery unused-service disable:")
    print("  - se_omapi / QTI Secure Element auto-start: disabled")
    print("  - NXP StrongBox advertisement/start: disabled")
    print("  - SPSS remoteproc0 forced boot: disabled")
    print("  - QTI KeyMint default / Gatekeeper / Weaver / QSEE / ADSP: unchanged")


def check(root: Path) -> None:
    errors: list[str] = []
    se_omapi = root / "system/etc/init/se_omapi.rc"
    if not se_omapi.is_file():
        errors.append("se_omapi override missing")
    else:
        t = se_omapi.read_text(encoding="utf-8")
        if "disabled" not in t or "interface aidl" in t or "start se_omapi" in t:
            errors.append("se_omapi is still startable/auto-started")

    se_rc = root / "vendor/etc/init/android.hardware.secure_element-service.qti.rc"
    if not se_rc.is_file() or "disabled" not in se_rc.read_text(encoding="utf-8"):
        errors.append("vendor.secure_element is not disabled")

    sb_rc = root / "vendor/etc/init/android.hardware.security.keymint-service.strongbox-nxp.rc"
    if not sb_rc.is_file():
        errors.append("StrongBox rc missing")
    else:
        t = sb_rc.read_text(encoding="utf-8")
        if "disabled" not in t or "interface aidl" in t:
            errors.append("StrongBox service remains startable/lazy")

    sb_manifest = root / "vendor/etc/vintf/manifest/android.hardware.security.keymint3-service.strongbox-nxp.xml"
    if sb_manifest.exists():
        errors.append("StrongBox VINTF fragment is still advertised")

    qcom_rc = root / "init.recovery.qcom.rc"
    if not qcom_rc.is_file():
        errors.append("init.recovery.qcom.rc missing")
    else:
        t = qcom_rc.read_text(encoding="utf-8")
        if "write /sys/class/remoteproc/remoteproc0/state start" in t:
            errors.append("SPSS remoteproc0 forced start still present")
        if "write /sys/kernel/boot_adsp/boot 1" not in t:
            errors.append("ADSP boot path was removed")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
    print("Tiro unused-service check OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="Tiro recovery root directory")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check(args.root)
    else:
        patch(args.root)
        check(args.root)


if __name__ == "__main__":
    main()
