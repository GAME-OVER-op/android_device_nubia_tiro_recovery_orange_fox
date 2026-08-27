#!/usr/bin/env python3
"""Ensure OrangeFox compact post-flash button styles/resources exist for tiro.

The known-good Red Magic recovery uses the native OrangeFox button styles
`btn_raised_s` and `btn_raised_s_hl`.  Some fox_14.1 source snapshots can miss
one side of the style -> image-resource chain, which causes GUIButton to log
"No image resource or fill specified for button" and leaves the control with
no usable background/geometry.

Keep the page XML native: do NOT add a child <image> to each <button>.  The
button style is responsible for both its font/text and its background.  This
script patches only missing/incomplete compact style/resource definitions in
the active OrangeFox theme.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NORMAL = "btn_raised_s"
HILITE = "btn_raised_s_hl"
MARKER_IMAGES = "TIRO_POSTFLASH_BUTTON_SHAPES"
MARKER_STYLES = "TIRO_POSTFLASH_BUTTON_STYLES"

RESOURCE_RE = {
    NORMAL: re.compile(r"\bname\s*=\s*['\"]btn_raised_s['\"]"),
    HILITE: re.compile(r"\bname\s*=\s*['\"]btn_raised_s_hl['\"]"),
}
STYLE_RE = {
    NORMAL: re.compile(r"<style\s+name\s*=\s*['\"]btn_raised_s['\"]\s*>(.*?)</style>", re.S),
    HILITE: re.compile(r"<style\s+name\s*=\s*['\"]btn_raised_s_hl['\"]\s*>(.*?)</style>", re.S),
}

STYLE_BLOCK = {
    NORMAL: (
        '\t\t<style name="btn_raised_s">\n'
        '\t\t\t<highlight color="%highlight_color%"/>\n'
        '\t\t\t<font resource="Secondary" color="%text%"/>\n'
        '\t\t\t<image resource="btn_raised_s"/>\n'
        '\t\t</style>'
    ),
    HILITE: (
        '\t\t<style name="btn_raised_s_hl">\n'
        '\t\t\t<highlight color="%highlight_color%"/>\n'
        '\t\t\t<font resource="Secondary" color="%text_hl_btn%"/>\n'
        '\t\t\t<image resource="btn_raised_s_hl"/>\n'
        '\t\t</style>'
    ),
}


def search_roots(src: Path) -> list[Path]:
    roots = [src / "bootable/recovery", src / "vendor/recovery", src / "vendor/twrp"]
    return [p for p in roots if p.is_dir()]


def has_resource(text: str, name: str) -> bool:
    return bool(RESOURCE_RE[name].search(text))


def style_ok(text: str, name: str) -> bool:
    m = STYLE_RE[name].search(text)
    if not m:
        return False
    body = m.group(1)
    expected_color = "%text_hl_btn%" if name == HILITE else "%text%"
    return (
        re.search(r"<font\b[^>]*\bresource\s*=\s*['\"]Secondary['\"]", body) is not None
        and expected_color in body
        and re.search(rf"<image\b[^>]*\bresource\s*=\s*['\"]{re.escape(name)}['\"]", body) is not None
    )


def discover_pairs(src: Path) -> list[tuple[Path, Path]]:
    pairs: set[tuple[Path, Path]] = set()
    for root in search_roots(src):
        for styles in root.rglob("styles.xml"):
            images = styles.with_name("images.xml")
            if not images.is_file():
                continue
            try:
                st = styles.read_text(encoding="utf-8", errors="replace")
                im = images.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            signals = (
                "btn_raised" in st,
                "btn_flat" in st,
                "btn_raised" in im,
                "btn_flat_qw" in im,
                "nav_empty" in im,
            )
            if any(signals):
                pairs.add((styles, images))
    return sorted(pairs)


def patch_images(path: Path, check_only: bool) -> bool:
    text = path.read_text(encoding="utf-8", errors="strict")
    missing = [n for n in (NORMAL, HILITE) if not has_resource(text, n)]
    if not missing:
        return True
    if check_only:
        print(f"ERROR: {path}: missing image resources: {', '.join(missing)}", file=sys.stderr)
        return False
    opening = re.search(r"<resources\b[^>]*>", text)
    if not opening:
        print(f"ERROR: {path}: no <resources> element", file=sys.stderr)
        return False
    lines = [f"\n\t\t<!-- {MARKER_IMAGES}: Red Magic 9 Pro compact post-flash buttons -->"]
    if NORMAL in missing:
        lines.append('\t\t<shape name="btn_raised_s" w="320" h="%btn_h%" radius="-1" color="%neutral_light%" />')
    if HILITE in missing:
        lines.append('\t\t<shape name="btn_raised_s_hl" w="320" h="%btn_h%" radius="-1" color="%accent%" />')
    lines.append("")
    text = text[: opening.end()] + "\n".join(lines) + text[opening.end() :]
    path.write_text(text, encoding="utf-8")
    return all(has_resource(text, n) for n in (NORMAL, HILITE))


def patch_styles(path: Path, check_only: bool) -> bool:
    text = path.read_text(encoding="utf-8", errors="strict")
    bad = [n for n in (NORMAL, HILITE) if not style_ok(text, n)]
    if not bad:
        return True
    if check_only:
        print(f"ERROR: {path}: missing/incomplete button styles: {', '.join(bad)}", file=sys.stderr)
        return False

    changed = False
    for name in bad:
        rx = STYLE_RE[name]
        if rx.search(text):
            text = rx.sub(STYLE_BLOCK[name], text, count=1)
        else:
            opening = re.search(r"<styles\b[^>]*>", text)
            if not opening:
                print(f"ERROR: {path}: no <styles> element", file=sys.stderr)
                return False
            injection = f"\n\t\t<!-- {MARKER_STYLES}: Red Magic 9 Pro compact post-flash buttons -->\n{STYLE_BLOCK[name]}\n"
            text = text[: opening.end()] + injection + text[opening.end() :]
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
    return all(style_ok(text, n) for n in (NORMAL, HILITE))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--check", action="store_true", help="verify only; do not modify files")
    args = parser.parse_args()

    src = args.source_root.resolve()
    if not src.is_dir():
        print(f"ERROR: OrangeFox source root not found: {src}", file=sys.stderr)
        return 2

    pairs = discover_pairs(src)
    if not pairs:
        print("ERROR: could not locate an OrangeFox styles.xml/images.xml theme pair", file=sys.stderr)
        for root in search_roots(src):
            print(f"  searched: {root}", file=sys.stderr)
        return 1

    ok = True
    for styles, images in pairs:
        ok &= patch_styles(styles, args.check)
        ok &= patch_images(images, args.check)
        if ok:
            print(f"Theme compact-button style/resource chain OK: {styles.parent}")

    if ok:
        mode = "verified" if args.check else "prepared"
        print(f"Tiro compact post-flash button theme {mode} in {len(pairs)} registry pair(s)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
