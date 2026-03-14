#!/usr/bin/env python3
"""Check split tree invariants from `wezterm cli list --format tree`.

Walks the PaneNode tree and verifies that at every split node:
- Horizontal: first.rows == second.rows == allocated.rows
- Horizontal: first.cols + 1 + second.cols == allocated.cols
- Vertical: first.cols == second.cols == allocated.cols
- Vertical: first.rows + 1 + second.rows == allocated.rows

Usage:
    wezterm cli list --format tree | python3 check-tree-invariants.py

Exit code 0 if all invariants hold, 1 if any violations found.
"""
import json
import sys


def check_node(node, allocated, path="root"):
    """Recursively check invariants. Returns list of violation strings."""
    violations = []

    if node == "Empty" or "Leaf" in node:
        return violations

    if "Split" not in node:
        return violations

    split = node["Split"]
    data = split["node"]
    direction = data["direction"]
    first = data["first"]
    second = data["second"]

    if direction == "Horizontal":
        # Both children must have same rows as allocated
        if first["rows"] != allocated["rows"]:
            violations.append(
                f"{path}: H-split first.rows={first['rows']} != "
                f"allocated.rows={allocated['rows']}"
            )
        if second["rows"] != allocated["rows"]:
            violations.append(
                f"{path}: H-split second.rows={second['rows']} != "
                f"allocated.rows={allocated['rows']}"
            )
        # Cols must sum
        total = first["cols"] + 1 + second["cols"]
        if total != allocated["cols"]:
            violations.append(
                f"{path}: H-split cols {first['cols']}+1+{second['cols']}"
                f"={total} != allocated.cols={allocated['cols']}"
            )
    elif direction == "Vertical":
        # Both children must have same cols as allocated
        if first["cols"] != allocated["cols"]:
            violations.append(
                f"{path}: V-split first.cols={first['cols']} != "
                f"allocated.cols={allocated['cols']}"
            )
        if second["cols"] != allocated["cols"]:
            violations.append(
                f"{path}: V-split second.cols={second['cols']} != "
                f"allocated.cols={allocated['cols']}"
            )
        # Rows must sum
        total = first["rows"] + 1 + second["rows"]
        if total != allocated["rows"]:
            violations.append(
                f"{path}: V-split rows {first['rows']}+1+{second['rows']}"
                f"={total} != allocated.rows={allocated['rows']}"
            )

    # Recurse into children
    violations.extend(check_node(split["left"], first, path=f"{path}.left"))
    violations.extend(check_node(split["right"], second, path=f"{path}.right"))

    return violations


def root_size(node):
    """Compute the root size of a PaneNode tree."""
    if "Split" in node:
        data = node["Split"]["node"]
        direction = data["direction"]
        first = data["first"]
        second = data["second"]
        if direction == "Horizontal":
            return {
                "rows": first["rows"],
                "cols": first["cols"] + 1 + second["cols"],
                "pixel_width": first.get("pixel_width", 0)
                + second.get("pixel_width", 0),
                "pixel_height": first.get("pixel_height", 0),
                "dpi": first.get("dpi", 0),
            }
        else:
            return {
                "rows": first["rows"] + 1 + second["rows"],
                "cols": first["cols"],
                "pixel_width": first.get("pixel_width", 0),
                "pixel_height": first.get("pixel_height", 0)
                + second.get("pixel_height", 0),
                "dpi": first.get("dpi", 0),
            }
    elif "Leaf" in node:
        return node["Leaf"]["size"]
    return None


def main():
    tabs = json.load(sys.stdin)
    total_violations = 0

    for tab in tabs:
        title = tab.get("tab_title", "?")
        tree = tab["tree"]
        size = root_size(tree)
        if size is None:
            continue

        violations = check_node(tree, size)
        if violations:
            total_violations += len(violations)
            print(f"tab ({title}): {len(violations)} violation(s)")
            for v in violations:
                print(f"  {v}")

    if total_violations == 0:
        print("All tree invariants hold.")
    else:
        print(f"\n{total_violations} total violation(s)")

    sys.exit(1 if total_violations else 0)


if __name__ == "__main__":
    main()
