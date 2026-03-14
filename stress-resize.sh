#!/usr/bin/env bash
# Stress test: rapidly adjust pane sizes and check for invariant violations.
#
# Creates an L-shaped layout on a separate mux server, then repeatedly
# adjusts dividers and resizes panes, checking for overflow after each round.
#
# Usage:
#   ./stress-resize.sh [--rounds N] [--socket PATH]
#
# If --socket is given, operates on that mux server. Otherwise, uses the
# default wezterm socket (your running session).
#
# WARNING: This modifies pane sizes in the target session. Use --socket
# with an isolated mux server to avoid disturbing your work.

set -euo pipefail

ROUNDS=50
SOCKET=""
PANE_ID=""
TAB_TITLE="stress-resize-$$"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rounds) ROUNDS="$2"; shift 2 ;;
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

check() {
    local json
    json=$(cli list --format json)
    echo "$json" | python3 track-pane-sizes.py --once 2>&1
    return $?
}

echo "=== Stress resize test: $ROUNDS rounds ==="
echo ""

# Find or create the L-shaped layout.
# Use the current active pane — split it, then split the right side.
echo "Setting up L-shaped layout..."

# Create horizontal split (left | right)
RIGHT_PANE=$(cli split-pane --right --percent 50)
echo "  horizontal split: right pane = $RIGHT_PANE"

# Create vertical sub-split on the right (top-right / bottom-right)
BOT_RIGHT=$(cli split-pane --pane-id "$RIGHT_PANE" --bottom --percent 50)
echo "  vertical sub-split: bottom-right pane = $BOT_RIGHT"

# Move the divider to create asymmetry
cli adjust-pane-size --pane-id "$RIGHT_PANE" --direction Down --amount 5
echo "  divider adjusted"
echo ""

# Check initial state
echo "--- Initial state ---"
check || true
echo ""

# Stress loop: rapidly adjust sizes in alternating directions
violations=0
for i in $(seq 1 "$ROUNDS"); do
    # Alternate between adjusting the vertical divider and doing
    # sequences of small adjustments in opposite directions
    dir1="Down"
    dir2="Up"
    if (( i % 2 == 0 )); then
        dir1="Up"
        dir2="Down"
    fi

    # Rapid-fire adjustments (simulates fast mouse drag)
    for _ in $(seq 1 5); do
        cli adjust-pane-size --pane-id "$RIGHT_PANE" --direction "$dir1" --amount 1 2>/dev/null || true
    done
    for _ in $(seq 1 3); do
        cli adjust-pane-size --pane-id "$RIGHT_PANE" --direction "$dir2" --amount 1 2>/dev/null || true
    done

    # Check for violations every 10 rounds
    if (( i % 10 == 0 )); then
        echo "--- Round $i/$ROUNDS ---"
        if ! check; then
            violations=$((violations + 1))
        fi
        echo ""
    fi
done

echo "--- Final state ---"
if ! check; then
    violations=$((violations + 1))
fi

echo ""
echo "=== Done: $violations violation check(s) with issues ==="
exit $((violations > 0 ? 1 : 0))
