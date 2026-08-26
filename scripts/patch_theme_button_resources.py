#!/usr/bin/env python3
"""Ensure OrangeFox has the two compact post-flash button resources used by tiro.

The tiro install-page overlay explicitly references btn_raised_s and
btn_raised_s_hl.  Some fox_14.1 source snapshots/styles contain the style names
but do not carry the matching resource declaration into the built theme.  Do
not replace the whole OrangeFox images.xml with an old device copy; instead,
locate the active OrangeFox resource registries and add only the missing shapes.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NORMAL = "btn_raised_s"
HILITE = "btn_raised_s_hl"
MARKER = "TIRO_POSTFLASH_BUTTON_SHAPES"

RESOURCE_RE = {
    NORMAL: re.compile(r"\bname\s*=\s*['\"]btn_raised_s['\"]"),
    HILITE: re.compile(r"\bname\s*=\s*['\"]btn_raised_s_hl['\"]"),
}


def has_resource(text: str, name: str) -> bool:
    return bool(RESOURCE_RE[name].search(text))


def search_roots(src: Path) -> list[Path]:
    roots = [
        src / "bootable/recovery",
        src / "vendor/recovery",
        src / "vendor/twrp",
    ]
    return [p for p in roots if p.is_dir()]


def discover(src: Path) -> list[Path]:
    candidates: set[Path] = set()
    roots = search_roots(src)

    # Strongest signal: a styles.xml that refers to the compact button styles,
    # with the resource registry next to it.
    for root in roots:
        for styles in root.rglob("styles.xml"):
            try:
                text = styles.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if NORMAL in text or HILITE in text:
                images = styles.with_name("images.xml")
                if images.is_file():
                    candidates.add(images)

    # OrangeFox layouts vary between branches.  Also accept image registries
    # that clearly contain the normal raised-button/theme resource family.
    for root in roots:
        for images in root.rglob("images.xml"):
            try:
                text = images.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "<resources" not in text:
                continue
            theme_signals = (
                'name="btn_raised"',
                "name='btn_raised'",
                "btn_flat_qw",
                "nav_empty",
                "actionbar_btn",
                "<mousecursor>",
            )
            if any(s in text for s in theme_signals):
                candidates.add(images)

    return sorted(candidates)


def patch_one(path: Path, check_only: bool) -> tuple[bool, bool]:
    text = path.read_text(encoding="utf-8", errors="strict")
    have_normal = has_resource(text, NORMAL)
    have_hilite = has_resource(text, HILITE)
    if have_normal and have_hilite:
        print(f"Theme button resources OK: {path}")
        return True, False

    if check_only:
        missing = [n for n, ok in ((NORMAL, have_normal), (HILITE, have_hilite)) if not ok]
        print(f"ERROR: {path}: missing {', '.join(missing)}", file=sys.stderr)
        return False, False

    opening = re.search(r"<resources\b[^>]*>", text)
    if not opening:
        print(f"ERROR: {path}: no <resources> element", file=sys.stderr)
        return False, False

    lines = [f"\n\t\t<!-- {MARKER}: Red Magic 9 Pro post-flash buttons -->"]
    if not have_normal:
        lines.append('\t\t<shape name="btn_raised_s" w="320" h="%btn_h%" radius="-1" color="%neutral_light%" />')
    if not have_hilite:
        lines.append('\t\t<shape name="btn_raised_s_hl" w="320" h="%btn_h%" radius="-1" color="%accent%" />')
    lines.append("")
    injection = "\n".join(lines)
    text = text[: opening.end()] + injection + text[opening.end() :]
    path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8", errors="strict")
    ok = has_resource(verify, NORMAL) and has_resource(verify, HILITE)
    if ok:
        print(f"Patched OrangeFox theme button resources: {path}")
    else:
        print(f"ERROR: failed to patch {path}", file=sys.stderr)
    return ok, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--check", action="store_true", help="verify only; do not modify files")
    args = parser.parse_args()

    src = args.source_root.resolve()
    if not src.is_dir():
        print(f"ERROR: OrangeFox source root not found: {src}", file=sys.stderr)
        return 2

    candidates = discover(src)
    if not candidates:
        print("ERROR: could not locate an OrangeFox theme images.xml registry", file=sys.stderr)
        for root in search_roots(src):
            print(f"  searched: {root}", file=sys.stderr)
        return 1

    all_ok = True
    for path in candidates:
        ok, _ = patch_one(path, args.check)
        all_ok &= ok

    if all_ok:
        mode = "verified" if args.check else "prepared"
        print(f"Tiro post-flash button resources {mode} in {len(candidates)} theme registry file(s)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
