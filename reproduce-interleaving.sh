#!/usr/bin/env bash
# End-to-end reproduction of the nested split resize overflow bug.
#
# Creates an L-shaped layout, computes sizes for two resize events,
# then sends interleaved per-pane Pdu::Resize messages using
# `wezterm cli resize-pane`. Checks for violations using both flat
# pane data and tree invariants.
#
# Usage:
#   ./reproduce-interleaving.sh [--socket PATH]
#
# Requires the fix branch's `resize-pane` and `list --format tree`
# CLI commands to be compiled and running.

set -euo pipefail

SOCKET=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --socket) SOCKET="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

cli() {
    if [[ -n "$SOCKET" ]]; then
        WEZTERM_UNIX_SOCKET="$SOCKET" wezterm cli --prefer-mux "$@"
    else
        wezterm cli "$@"
    fi
}

echo "=== Nested split resize interleaving reproduction ==="
echo ""

# Step 1: Create L-shaped layout
echo "Creating L-shaped layout..."
LEFT_PANE=$(cli list --format json | python3 -c "
import json, sys
panes = json.load(sys.stdin)
# Find a tab with just 1 pane to use as our test bed, or use active pane
for p in panes:
    if p.get('is_active'):
        print(p['pane_id'])
        break
")
echo "  Active pane: $LEFT_PANE"

RIGHT_PANE=$(cli split-pane --pane-id "$LEFT_PANE" --right --percent 50)
echo "  Right pane: $RIGHT_PANE"

BOT_RIGHT=$(cli split-pane --pane-id "$RIGHT_PANE" --bottom --percent 50)
echo "  Bottom-right pane: $BOT_RIGHT"

# Make it asymmetric
cli adjust-pane-size --pane-id "$RIGHT_PANE" --direction Down --amount 5
echo "  Divider adjusted"

# Step 2: Record current sizes
echo ""
echo "Recording baseline sizes..."
BASELINE=$(cli list --format json)
echo "$BASELINE" | python3 -c "
import json, sys
panes = json.load(sys.stdin)
for p in sorted(panes, key=lambda x: (x['top_row'], x['left_col'])):
    s = p['size']
    print(f\"  pane {p['pane_id']:>3}: {s['cols']}x{s['rows']} at ({p['left_col']},{p['top_row']})\")
"

# Step 3: Compute sizes for two different resize events
# We'll resize individual panes to inconsistent sizes
echo ""
echo "Sending interleaved resize PDUs..."

# Get current sizes
read -r LEFT_ROWS LEFT_COLS RIGHT_ROWS RIGHT_COLS BOT_ROWS BOT_COLS <<< $(
    echo "$BASELINE" | python3 -c "
import json, sys
panes = json.load(sys.stdin)
by_id = {p['pane_id']: p for p in panes}
l = by_id[$LEFT_PANE]['size']
r = by_id[$RIGHT_PANE]['size']
b = by_id[$BOT_RIGHT]['size']
print(f\"{l['rows']} {l['cols']} {r['rows']} {r['cols']} {b['rows']} {b['cols']}\")
")

# Event 1 sizes: grow by 10 rows (simulated)
E1_LEFT_ROWS=$((LEFT_ROWS + 10))
E1_RIGHT_ROWS=$((RIGHT_ROWS + 5))
E1_BOT_ROWS=$((BOT_ROWS + 4))

# Event 2 sizes: grow by 15 rows (simulated)
E2_LEFT_ROWS=$((LEFT_ROWS + 15))
E2_RIGHT_ROWS=$((RIGHT_ROWS + 8))
E2_BOT_ROWS=$((BOT_ROWS + 6))

# Send interleaved: left from E2, top-right from E2, bottom-right from E1 (STALE)
echo "  resize-pane $LEFT_PANE: ${LEFT_COLS}x${E2_LEFT_ROWS} (E2)"
cli resize-pane --pane-id "$LEFT_PANE" --rows "$E2_LEFT_ROWS" --cols "$LEFT_COLS" 2>/dev/null || echo "  (resize-pane not available — needs fix branch binary)"

echo "  resize-pane $RIGHT_PANE: ${RIGHT_COLS}x${E2_RIGHT_ROWS} (E2)"
cli resize-pane --pane-id "$RIGHT_PANE" --rows "$E2_RIGHT_ROWS" --cols "$RIGHT_COLS" 2>/dev/null || echo "  (resize-pane not available)"

echo "  resize-pane $BOT_RIGHT: ${BOT_COLS}x${E1_BOT_ROWS} (E1 — STALE)"
cli resize-pane --pane-id "$BOT_RIGHT" --rows "$E1_BOT_ROWS" --cols "$BOT_COLS" 2>/dev/null || echo "  (resize-pane not available)"

# Step 4: Check for violations
echo ""
echo "=== Checking for violations ==="

# Flat check
echo "--- Flat pane check ---"
cli list --format json | python3 track-pane-sizes.py --once 2>&1 || true

# Tree check (if available)
echo ""
echo "--- Tree invariant check ---"
cli list --format tree 2>/dev/null | python3 check-tree-invariants.py 2>&1 || echo "(tree format not available — needs fix branch binary)"

# Step 5: Clean up — kill the panes we created
echo ""
echo "Cleaning up..."
cli kill-pane --pane-id "$BOT_RIGHT" 2>/dev/null || true
cli kill-pane --pane-id "$RIGHT_PANE" 2>/dev/null || true
echo "Done."
