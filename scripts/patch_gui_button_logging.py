#!/usr/bin/env python3
"""Add non-invasive diagnostics for malformed/transparent OrangeFox GUI buttons.

The stock OrangeFox message only says that a button has neither an image nor a
fill.  On-device this is hard to map back to a theme XML element.  This patch
keeps the warning but appends the button style, placement, first action and
condition so the exact XML element can be identified from recovery.log.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARKER = "TIRO_GUI_BUTTON_DIAGNOSTICS"

OLD = '''\tif (!hasFill && mButtonImg == NULL) {
\t\tLOGERR("No image resource or fill specified for button.\\n");
\t}
'''

NEW = '''\tif (!hasFill && mButtonImg == NULL) {
\t\t// TIRO_GUI_BUTTON_DIAGNOSTICS: preserve the upstream warning, but add
\t\t// enough XML context to identify the offending theme element on-device.
\t\tauto* style_attr = node->first_attribute("style");
\t\txml_node<>* placement_node = FindNode(node, "placement");
\t\tauto* x_attr = placement_node ? placement_node->first_attribute("x") : nullptr;
\t\tauto* y_attr = placement_node ? placement_node->first_attribute("y") : nullptr;
\t\tauto* w_attr = placement_node ? placement_node->first_attribute("w") : nullptr;
\t\tauto* h_attr = placement_node ? placement_node->first_attribute("h") : nullptr;
\t\tauto* placement_attr = placement_node ? placement_node->first_attribute("placement") : nullptr;
\t\txml_node<>* action_node = FindNode(node, "action");
\t\tauto* action_attr = action_node ? action_node->first_attribute("function") : nullptr;
\t\txml_node<>* condition_node = FindNode(node, "condition");
\t\tauto* var1_attr = condition_node ? condition_node->first_attribute("var1") : nullptr;
\t\tauto* var2_attr = condition_node ? condition_node->first_attribute("var2") : nullptr;
\t\tLOGERR("No image resource or fill specified for button [TIRO_GUI_BUTTON_DIAGNOSTICS]: "
\t\t       "style='%s' placement{x='%s',y='%s',w='%s',h='%s',mode='%s'} "
\t\t       "action='%s' condition{var1='%s',var2='%s'}\\n",
\t\t       style_attr ? style_attr->value() : "<none>",
\t\t       x_attr ? x_attr->value() : "<none>",
\t\t       y_attr ? y_attr->value() : "<none>",
\t\t       w_attr ? w_attr->value() : "<none>",
\t\t       h_attr ? h_attr->value() : "<none>",
\t\t       placement_attr ? placement_attr->value() : "<none>",
\t\t       action_attr ? action_attr->value() : "<none>",
\t\t       var1_attr ? var1_attr->value() : "<none>",
\t\t       var2_attr ? var2_attr->value() : "<none>");
\t}
'''


def patch_file(path: Path) -> bool:
    text = path.read_text()
    if MARKER in text:
        print(f"GUI button diagnostics already present: {path}")
        return True
    if OLD not in text:
        print(
            "ERROR: expected OrangeFox GUIButton warning block was not found; "
            "upstream gui/button.cpp may have changed",
            file=sys.stderr,
        )
        return False
    path.write_text(text.replace(OLD, NEW, 1))
    print(f"Patched GUI button diagnostics: {path}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("button_cpp", type=Path)
    args = ap.parse_args()
    if not args.button_cpp.is_file():
        print(f"ERROR: file not found: {args.button_cpp}", file=sys.stderr)
        return 2
    return 0 if patch_file(args.button_cpp) else 1


if __name__ == "__main__":
    raise SystemExit(main())
