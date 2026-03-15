#!/usr/bin/env bash
set -euo pipefail

DEST="$HOME/wezterm-test"
SRC="/code/wezterm/target/release"

usage() {
    echo "Usage: ./deploy.sh [--restart]"
    echo ""
    echo "  (no flags)  Build, save session, copy binaries"
    echo "  --restart   Also kill the mux server (Mac reconnect triggers new binary)"
    echo ""
    echo "After --restart, reconnect from Mac then run:"
    echo "  cd /code/wezterm && python3 wez-tabs restore"
}

RESTART=false
for arg in "$@"; do
    case "$arg" in
        --restart) RESTART=true ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown arg: $arg"; usage; exit 1 ;;
    esac
done

echo "=== Step 1: Build ==="
cargo build --release -p wezterm -p wezterm-mux-server 2>&1 | tail -3
echo ""

echo "=== Step 2: Save current session ==="
cd /code/wezterm
python3 wez-tabs save
echo ""

echo "=== Step 3: Deploy binaries ==="
for bin in wezterm wezterm-mux-server; do
    rm -f "$DEST/$bin"
    cp "$SRC/$bin" "$DEST/$bin"
    echo "  $bin → $DEST/$bin"
done
echo "  Version: $($DEST/wezterm --version 2>&1)"
echo ""

if $RESTART; then
    echo "=== Step 4: Killing mux server ==="
    PID=$(pgrep -f 'wezterm-mux-server.*pid-file' | head -1 || true)
    if [ -n "$PID" ]; then
        kill "$PID"
        echo "  Killed PID $PID"
        echo ""
        echo "Reconnect from Mac. Your tabs will be restored automatically"
        echo "(the new server reads session.json on startup)."
        echo ""
        echo "To also relaunch AI agents (claude, codex):"
        echo "  cd /code/wezterm && python3 wez-tabs restore"
    else
        echo "  No running mux server found"
    fi
else
    echo "Binaries deployed. Run with --restart to kill the server."
    echo "Or manually: kill \$(pgrep -f 'wezterm-mux-server.*pid-file' | head -1)"
fi
