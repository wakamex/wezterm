#!/usr/bin/env python3

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, unquote


def run_json(cmd: list[str]) -> object:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def run_text(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def measure_ms(fn) -> float:
    start = time.perf_counter()
    fn()
    end = time.perf_counter()
    return (end - start) * 1000.0


def summarize(name: str, samples: list[float]) -> str:
    ordered = sorted(samples)
    p50 = statistics.median(ordered)
    p95_index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95))))
    p95 = ordered[p95_index]
    return (
        f"{name}: n={len(samples)} "
        f"min={ordered[0]:.1f}ms p50={p50:.1f}ms p95={p95:.1f}ms max={ordered[-1]:.1f}ms"
    )


def decode_cwd(cwd: str) -> str:
    if cwd.startswith("file://"):
        parsed = urlparse(cwd)
        return unquote(parsed.path) or cwd
    return cwd


def choose_window(rows: list[dict], pane_id: int | None) -> tuple[int, int, list[dict]]:
    if pane_id is not None:
        anchor = next((row for row in rows if row["pane_id"] == pane_id), None)
        if anchor is None:
            raise SystemExit(f"pane {pane_id} not found")
        window_id = anchor["window_id"]
        window_rows = [row for row in rows if row["window_id"] == window_id]
        return window_id, anchor["pane_id"], window_rows

    by_window: dict[int, list[dict]] = {}
    for row in rows:
        by_window.setdefault(row["window_id"], []).append(row)

    ranked = sorted(by_window.items(), key=lambda item: (-len({r["tab_id"] for r in item[1]}), item[0]))
    for window_id, window_rows in ranked:
        tabs = {row["tab_id"] for row in window_rows}
        if len(tabs) >= 2:
            active = next((row for row in window_rows if row.get("is_active")), window_rows[0])
            return window_id, active["pane_id"], window_rows

    raise SystemExit("need at least two tabs in one window to benchmark activation")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark mux tab activation/spawn latency")
    parser.add_argument("--wakterm", default="./target/debug/wakterm")
    parser.add_argument("--pane-id", type=int, help="anchor pane id; defaults to active pane in a window with >=2 tabs")
    parser.add_argument("--activate-iterations", type=int, default=50)
    parser.add_argument("--spawn-iterations", type=int, default=10)
    parser.add_argument("--skip-spawn", action="store_true")
    parser.add_argument("--cwd", default=None, help="cwd for spawned tabs; defaults to anchor pane cwd")
    args = parser.parse_args()

    wakterm = str(Path(args.wakterm))
    base = [wakterm, "cli"]
    rows = run_json(base + ["list", "--format", "json"])
    if not isinstance(rows, list):
        raise SystemExit("unexpected cli list output")

    window_id, anchor_pane_id, window_rows = choose_window(rows, args.pane_id)
    tabs = sorted({row["tab_id"] for row in window_rows})
    if len(tabs) < 2:
        raise SystemExit("need at least two tabs in one window to benchmark activation")

    anchor_row = next(row for row in window_rows if row["pane_id"] == anchor_pane_id)
    first_tab, second_tab = tabs[0], tabs[1]
    spawn_cwd = args.cwd or decode_cwd(anchor_row["cwd"])

    print(f"window={window_id} anchor_pane={anchor_pane_id} tabs={first_tab},{second_tab} cwd={spawn_cwd}")

    activate_samples: list[float] = []
    target_index = 1
    activation_error = None
    for _ in range(args.activate_iterations):
        try:
            activate_samples.append(
                measure_ms(
                    lambda target_index=target_index: run_text(
                        base + ["activate-tab", "--tab-index", str(target_index)]
                    )
                )
            )
        except subprocess.CalledProcessError as err:
            activation_error = err.stderr.strip() or err.stdout.strip() or str(err)
            break
        target_index = 0 if target_index == 1 else 1

    if activate_samples:
        print(summarize("activate-tab", activate_samples))
    if activation_error:
        print(f"activate-tab: unavailable ({activation_error})")

    if not args.skip_spawn:
        spawn_samples: list[float] = []
        cleanup_failures = 0
        for _ in range(args.spawn_iterations):
            def spawn_once() -> str:
                return run_text(base + ["spawn", "--pane-id", str(anchor_pane_id), "--cwd", spawn_cwd])

            start = time.perf_counter()
            new_pane = spawn_once()
            end = time.perf_counter()
            spawn_samples.append((end - start) * 1000.0)
            try:
                run_text(base + ["kill-pane", "--pane-id", new_pane])
            except subprocess.CalledProcessError:
                cleanup_failures += 1
            run_text(base + ["activate-tab", "--pane-id", str(anchor_pane_id), "--tab-id", str(first_tab)])

        print(summarize("spawn-tab", spawn_samples))
        if cleanup_failures:
            print(f"cleanup_failures={cleanup_failures}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
