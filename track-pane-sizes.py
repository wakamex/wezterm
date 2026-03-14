#!/usr/bin/env python3
"""Monitor wezterm pane sizes and detect split tree invariant violations.

Polls `wezterm cli list --format json` and checks that panes within each
tab form a consistent grid: all columns should have the same total height,
all rows the same total width.

Usage:
    python3 track-pane-sizes.py [--interval SECS] [--socket PATH] [--json]

When a violation is detected, prints the full tab state. With --json,
emits structured JSON records suitable for replaying as test cases.
"""
import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class PaneRect:
    pane_id: int
    left_col: int
    top_row: int
    cols: int
    rows: int
    pixel_width: int
    pixel_height: int

    @property
    def right_col(self):
        return self.left_col + self.cols

    @property
    def bottom_row(self):
        return self.top_row + self.rows


def get_panes(socket_path=None):
    """Fetch pane list from wezterm CLI."""
    cmd = ["wezterm", "cli", "list", "--format", "json"]
    if socket_path:
        cmd = ["wezterm", "cli", "--prefer-mux", "list", "--format", "json"]
        # Set WEZTERM_UNIX_SOCKET for targeting a specific server
        env = {"WEZTERM_UNIX_SOCKET": socket_path}
    else:
        env = None

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, env=env,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def panes_to_rects(panes):
    """Convert raw pane JSON to PaneRect list, grouped by tab."""
    tabs = defaultdict(list)
    tab_meta = {}
    for p in panes:
        tid = p["tab_id"]
        s = p["size"]
        tabs[tid].append(PaneRect(
            pane_id=p["pane_id"],
            left_col=p["left_col"],
            top_row=p["top_row"],
            cols=s["cols"],
            rows=s["rows"],
            pixel_width=s["pixel_width"],
            pixel_height=s["pixel_height"],
        ))
        if tid not in tab_meta:
            tab_meta[tid] = {
                "tab_title": p.get("tab_title", ""),
                "window_id": p.get("window_id"),
            }
    return tabs, tab_meta


def check_tab_invariants(rects):
    """Check split tree invariants for a set of panes in one tab.

    Returns a list of violation dicts (empty = all good).

    Strategy: group panes by left_col to find vertical columns, and by
    top_row to find horizontal rows. Within each column, check that all
    panes have the same width and that heights sum correctly. Across
    columns, check that total heights match.
    """
    if len(rects) < 2:
        return []

    violations = []

    # --- Vertical columns: group by left_col ---
    col_groups = defaultdict(list)
    for r in rects:
        col_groups[r.left_col].append(r)

    column_heights = {}
    for left_col, group in col_groups.items():
        group.sort(key=lambda r: r.top_row)

        # Check width consistency only among vertically adjacent panes
        # (panes that form a contiguous column with dividers between them).
        # Panes at the same left_col but non-adjacent are at different
        # nesting levels and may legitimately have different widths.
        for i in range(1, len(group)):
            if group[i].top_row == group[i - 1].bottom_row + 1:
                if group[i].cols != group[i - 1].cols:
                    violations.append({
                        "type": "column_width_inconsistency",
                        "column_left": left_col,
                        "pane_ids": [group[i - 1].pane_id, group[i].pane_id],
                        "widths": {
                            group[i - 1].pane_id: group[i - 1].cols,
                            group[i].pane_id: group[i].cols,
                        },
                    })

        # Total height = sum of rows + (n-1) dividers between them
        total_rows = sum(r.rows for r in group) + (len(group) - 1)
        column_heights[left_col] = (total_rows, group)

        # Check adjacency: each pane should start right after the previous
        for i in range(1, len(group)):
            expected_top = group[i - 1].bottom_row + 1  # +1 for divider
            actual_top = group[i].top_row
            if actual_top != expected_top:
                violations.append({
                    "type": "adjacency_gap",
                    "axis": "vertical",
                    "column": left_col,
                    "pane_above": group[i - 1].pane_id,
                    "pane_below": group[i].pane_id,
                    "expected_top": expected_top,
                    "actual_top": actual_top,
                    "gap": actual_top - expected_top,
                })

    # All columns should have the same total height.
    # Use single-pane columns as the reference (ground truth) when
    # available, since they can't have internal sum errors.
    if len(column_heights) > 1:
        heights = {k: v[0] for k, v in column_heights.items()}
        single_pane_heights = {
            k: h for k, h in heights.items()
            if len(column_heights[k][1]) == 1
        }
        if single_pane_heights:
            reference_h = next(iter(single_pane_heights.values()))
        else:
            reference_h = max(heights.values())

        for left_col, h in heights.items():
            if h != reference_h and left_col not in single_pane_heights:
                group = column_heights[left_col][1]
                violations.append({
                    "type": "column_height_mismatch",
                    "column_left": left_col,
                    "column_height": h,
                    "expected_height": reference_h,
                    "delta": h - reference_h,
                    "pane_ids": [r.pane_id for r in group],
                    "pane_rows": [r.rows for r in group],
                })

    return violations


def format_tab_state(tab_id, meta, rects, violations):
    """Format a tab's state for human-readable output."""
    lines = []
    title = meta.get("tab_title", "")
    lines.append(f"tab {tab_id} ({title}): {len(rects)} panes")
    for r in sorted(rects, key=lambda r: (r.top_row, r.left_col)):
        lines.append(
            f"  pane {r.pane_id:>3}: pos=({r.left_col},{r.top_row}) "
            f"size={r.cols}x{r.rows} px={r.pixel_width}x{r.pixel_height}"
        )
    for v in violations:
        vtype = v["type"]
        if vtype == "column_height_mismatch":
            lines.append(
                f"  ** HEIGHT: col {v['column_left']} panes {v['pane_ids']} "
                f"rows {v['pane_rows']} sum to {v['column_height']} "
                f"(expected {v['expected_height']}, {v['delta']:+d})"
            )
        elif vtype == "row_width_mismatch":
            lines.append(
                f"  ** WIDTH: row {v['row_top']} panes {v['pane_ids']} "
                f"cols {v['pane_cols']} sum to {v['row_width']} "
                f"(expected {v['expected_width']}, {v['delta']:+d})"
            )
        elif vtype == "column_width_inconsistency":
            lines.append(
                f"  ** COL WIDTH: col {v['column_left']} panes have "
                f"different widths: {v['widths']}"
            )
        elif vtype == "adjacency_gap":
            lines.append(
                f"  ** GAP: pane {v['pane_above']}→{v['pane_below']} "
                f"at col {v['column']}: gap={v['gap']} rows"
            )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor wezterm pane sizes for split tree violations"
    )
    parser.add_argument(
        "--interval", type=float, default=1.0,
        help="Polling interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--socket", type=str, default=None,
        help="WEZTERM_UNIX_SOCKET path to target a specific mux server",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit structured JSON records on violations",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Check once and exit (don't loop)",
    )
    args = parser.parse_args()

    last_state = {}
    violation_count = 0

    while True:
        panes = get_panes(args.socket)
        if panes is None:
            if not args.once:
                time.sleep(args.interval)
                continue
            else:
                print("Failed to get pane list", file=sys.stderr)
                sys.exit(1)

        tabs, tab_meta = panes_to_rects(panes)

        for tab_id, rects in tabs.items():
            violations = check_tab_invariants(rects)

            # Build a fingerprint of current state to detect changes
            state_key = tuple(
                (r.pane_id, r.left_col, r.top_row, r.cols, r.rows)
                for r in sorted(rects, key=lambda r: r.pane_id)
            )

            prev_state = last_state.get(tab_id)
            state_changed = prev_state != state_key
            last_state[tab_id] = state_key

            if violations:
                violation_count += 1
                ts = datetime.now(timezone.utc).isoformat()

                if args.json:
                    record = {
                        "timestamp": ts,
                        "tab_id": tab_id,
                        "tab_title": tab_meta[tab_id].get("tab_title", ""),
                        "panes": [asdict(r) for r in rects],
                        "violations": violations,
                    }
                    print(json.dumps(record), flush=True)
                else:
                    print(f"\n[{ts}] VIOLATION #{violation_count}")
                    print(format_tab_state(
                        tab_id, tab_meta[tab_id], rects, violations
                    ), flush=True)

            elif state_changed and not args.json and not args.once:
                # State changed but no violations — log clean state
                ts = datetime.now(timezone.utc).isoformat()
                print(f"[{ts}] tab {tab_id}: {len(rects)} panes, OK", flush=True)

        if args.once:
            sys.exit(1 if violation_count > 0 else 0)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
