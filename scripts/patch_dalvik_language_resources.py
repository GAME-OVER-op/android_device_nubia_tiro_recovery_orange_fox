#!/usr/bin/env python3
"""Add Tiro Dalvik-only post-flash strings to every OrangeFox language file.

The stock OrangeFox post-flash page wipes /cache + Dalvik and therefore has no
standalone button label that is guaranteed to exist in every language. Tiro has
no usable /cache partition, so its overlay offers Dalvik-only wipe. This patcher
creates device-specific strings in each language, reusing existing localized
Dalvik strings whenever possible and falling back to universally present
`dalvik` or English text.
"""
from __future__ import annotations
import argparse
import html
import re
from pathlib import Path

MARKER = "TIRO_DALVIK_ONLY_POSTFLASH_STRINGS"
KEYS = (
    "tiro_wipe_dalvik_btn",
    "tiro_wipe_dalvik_confirm",
    "tiro_wiping_dalvik",
    "tiro_wipe_dalvik_complete",
)

STR_RE = re.compile(r'<string\s+name=["\']([^"\']+)["\']>(.*?)</string>', re.S)

def get_value(text: str, key: str) -> str | None:
    for name, value in STR_RE.findall(text):
        if name == key:
            return value.strip()
    return None

def candidate_files(root: Path):
    for p in root.rglob("*.xml"):
        if "languages" not in {part.lower() for part in p.parts}:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "<language" in text and "<resources>" in text and 'name="dalvik"' in text:
            yield p, text

def desired_values(text: str, filename: str = "") -> dict[str, str]:
    # Some upstream ru_RU strings in the known-good theme are mistranslated
    # (for example, wiping_dalvik says "Attempting decryption..."). Keep the
    # Tiro-specific Dalvik-only UI correct for the two Russian language files.
    if filename in {"ru.xml", "ru_RU.xml"}:
        return {
            "tiro_wipe_dalvik_btn": "Очистить Dalvik",
            "tiro_wipe_dalvik_confirm": "Очистить Dalvik?",
            "tiro_wiping_dalvik": "Очистка Dalvik...",
            "tiro_wipe_dalvik_complete": "Очистка Dalvik завершена",
        }
    dalvik = get_value(text, "dalvik") or "Dalvik / ART Cache"
    confirm = get_value(text, "wipe_dalvik_confirm") or dalvik
    wiping = get_value(text, "wiping_dalvik") or f"{dalvik}..."
    done = get_value(text, "dalvik_done") or f"{dalvik} complete"
    return {
        "tiro_wipe_dalvik_btn": confirm,
        "tiro_wipe_dalvik_confirm": confirm,
        "tiro_wiping_dalvik": wiping,
        "tiro_wipe_dalvik_complete": done,
    }

def patch_file(p: Path, text: str) -> bool:
    values = desired_values(text, p.name)
    missing = [k for k in KEYS if get_value(text, k) is None]
    if not missing:
        return False
    lines = [f"\t\t<!-- {MARKER} -->"]
    for key in missing:
        # Existing values are raw XML inner text, so preserve entities such as &amp;.
        lines.append(f'\t\t<string name="{key}">{values[key]}</string>')
    block = "\n" + "\n".join(lines) + "\n"
    if "</resources>" not in text:
        raise RuntimeError(f"{p}: missing </resources>")
    text = text.replace("</resources>", block + "\t</resources>", 1)
    p.write_text(text, encoding="utf-8")
    return True

def check(root: Path) -> int:
    files = list(candidate_files(root))
    if not files:
        raise SystemExit("ERROR: no OrangeFox language XML files found")
    bad = []
    for p, text in files:
        for key in KEYS:
            if get_value(text, key) is None:
                bad.append(f"{p}: missing {key}")
    if bad:
        raise SystemExit("ERROR: Tiro Dalvik language patch incomplete:\n" + "\n".join(bad[:50]))
    print(f"Tiro Dalvik language resources OK in {len(files)} language files")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fox_src", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return check(args.fox_src)
    files = list(candidate_files(args.fox_src))
    if not files:
        raise SystemExit("ERROR: no OrangeFox language XML files found")
    changed = 0
    for p, text in files:
        changed += int(patch_file(p, text))
    print(f"Patched Tiro Dalvik strings in {changed}/{len(files)} language files")
    return check(args.fox_src)

if __name__ == "__main__":
    raise SystemExit(main())
