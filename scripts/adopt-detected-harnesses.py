#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


HARNESSES = ("claude", "codex", "gemini", "opencode")
DEFAULT_COMMANDS = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
    "opencode": "opencode",
}
NODE_WRAPPERS = {"node", "node.exe", "bun", "bun.exe"}
HARNESS_PROC_HINTS = {
    "claude": ("claude",),
    "codex": ("codex",),
    "gemini": ("gemini",),
    "opencode": ("opencode",),
}
CLAUDE_DIR = Path(
    os.environ.get("WAKTERM_AGENT_CLAUDE_DIR", "~/.claude/projects")
).expanduser()
CODEX_DIR = Path(
    os.environ.get("WAKTERM_AGENT_CODEX_DIR", "~/.codex/sessions")
).expanduser()
OPENCODE_DB = Path(
    os.environ.get(
        "WAKTERM_AGENT_OPENCODE_DB", "~/.local/share/opencode/opencode.db"
    )
).expanduser()
GEMINI_DIR = Path(os.environ.get("WAKTERM_AGENT_GEMINI_DIR", "~/.gemini/tmp")).expanduser()
_codex_cache: dict[str, str] = {}
_codex_cache_t = 0.0


@dataclass
class TtySnapshot:
    tokens: set[str]
    commands: list[str]
    foreground_command: str | None


@dataclass
class Candidate:
    pane_id: int
    harness: str
    source: str
    title: str
    cwd: str
    cwd_leaf: str | None
    tty_name: str | None
    process_tokens: list[str]
    foreground_command: str | None
    session_hint: str | None
    proposed_name: str
    proposed_cmd: str
    already_adopted: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detect likely manual harness panes and optionally adopt them as agents. "
            "Defaults to dry-run."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform adoption instead of printing the plan",
    )
    parser.add_argument(
        "--pane-id",
        type=int,
        action="append",
        default=[],
        help="limit detection/adoption to the specified pane id; repeat to target multiple panes",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit candidate/result data as JSON",
    )
    parser.add_argument(
        "--prefer-mux",
        action="store_true",
        help="pass --prefer-mux to `wakterm cli`",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="pass --no-auto-start to `wakterm cli`",
    )
    parser.add_argument(
        "--class",
        dest="class_name",
        help="pass --class to `wakterm cli` when targeting a GUI instance",
    )
    parser.add_argument(
        "--wakterm-bin",
        default=os.environ.get("WAKTERM_BIN", "wakterm"),
        help="wakterm executable to invoke (default: %(default)s)",
    )
    return parser.parse_args()


def cli_base(args: argparse.Namespace) -> list[str]:
    cmd = [args.wakterm_bin, "cli"]
    if args.prefer_mux:
        cmd.append("--prefer-mux")
    if args.no_auto_start:
        cmd.append("--no-auto-start")
    if args.class_name:
        cmd.extend(["--class", args.class_name])
    return cmd


def run_json_command(cmd: list[str]) -> Any:
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(f"{' '.join(cmd)} failed: {message}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{' '.join(cmd)} returned invalid JSON: {exc}") from exc


def infer_harness(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        lowered = value.lower()
        for harness in HARNESSES:
            if harness in lowered:
                return harness
    return None


def normalize_tty_name(tty_name: str | None) -> str | None:
    if not tty_name:
        return None
    if tty_name.startswith("/dev/"):
        return tty_name[len("/dev/") :]
    return tty_name


def parse_cwd(cwd_url: str | None) -> str:
    if not cwd_url:
        return ""
    if cwd_url.startswith("file://"):
        return unquote(urlparse(cwd_url).path).rstrip("/")
    return cwd_url.rstrip("/")


def extract_command_tokens(command: str) -> set[str]:
    tokens = set()
    for part in command.strip().split():
        if not part or part.startswith("-"):
            continue
        tokens.add(Path(part).name.lower())
    return tokens


def inspect_tty_processes(tty_name: str | None) -> TtySnapshot | None:
    tty_selector = normalize_tty_name(tty_name)
    if not tty_selector:
        return None

    completed = subprocess.run(
        ["ps", "-t", tty_selector, "-o", "stat=", "-o", "args="],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None

    commands: list[str] = []
    tokens: set[str] = set()
    foreground_command = None

    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        stat = parts[0]
        command = parts[1]
        commands.append(command)
        tokens.update(extract_command_tokens(command))
        if "+" in stat:
            foreground_command = command

    if not commands:
        return None

    return TtySnapshot(
        tokens=tokens,
        commands=commands,
        foreground_command=foreground_command or commands[-1],
    )


def session_hint(session: Path | tuple[Path, str] | None) -> str | None:
    if session is None:
        return None
    if isinstance(session, tuple):
        return f"{session[0]}#{session[1]}"
    return str(session)


def session_mtime(session: Path | tuple[Path, str] | None) -> float:
    if session is None:
        return 0.0
    if isinstance(session, tuple):
        try:
            return session[0].stat().st_mtime
        except OSError:
            return 0.0
    try:
        return session.stat().st_mtime
    except OSError:
        return 0.0


def claude_is_interactive(path: Path) -> bool:
    try:
        with path.open() as file_obj:
            first = json.loads(file_obj.readline())
        return first.get("type") != "queue-operation"
    except (json.JSONDecodeError, OSError):
        return True


def find_claude_session(cwd: str) -> Path | None:
    if not cwd:
        return None
    project_dir = CLAUDE_DIR / cwd.replace("/", "-")
    if not project_dir.is_dir():
        return None
    files = [path for path in project_dir.glob("*.jsonl") if claude_is_interactive(path)]
    if not files:
        return None
    return max(files, key=lambda path: session_mtime(path))


def refresh_codex_cache() -> None:
    global _codex_cache
    global _codex_cache_t

    now = time.time()
    if now - _codex_cache_t <= 5:
        return

    cache: dict[str, str] = {}
    for days_ago in range(2):
        t = time.gmtime(now - days_ago * 86400)
        day = CODEX_DIR / f"{t.tm_year:04d}/{t.tm_mon:02d}/{t.tm_mday:02d}"
        if not day.is_dir():
            continue
        for path in day.glob("rollout-*.jsonl"):
            path_str = str(path)
            if path_str in cache:
                continue
            try:
                with path.open() as file_obj:
                    meta = json.loads(file_obj.readline())
                cache[path_str] = meta.get("payload", {}).get("cwd", "")
            except (json.JSONDecodeError, OSError):
                continue

    _codex_cache = cache
    _codex_cache_t = now


def find_codex_session(cwd: str) -> Path | None:
    if not cwd:
        return None
    refresh_codex_cache()

    best = None
    best_mtime = 0.0
    for path_str, session_cwd in _codex_cache.items():
        if session_cwd != cwd:
            continue
        path = Path(path_str)
        mtime = session_mtime(path)
        if mtime > best_mtime:
            best = path
            best_mtime = mtime
    return best


def find_opencode_session(cwd: str) -> tuple[Path, str] | None:
    if not cwd or not OPENCODE_DB.exists():
        return None
    try:
        con = sqlite3.connect(str(OPENCODE_DB), timeout=2)
        row = con.execute(
            "SELECT id FROM session WHERE directory = ? ORDER BY rowid DESC LIMIT 1",
            (cwd,),
        ).fetchone()
        con.close()
    except (sqlite3.Error, OSError):
        return None
    if not row:
        return None
    return (OPENCODE_DB, str(row[0]))


def find_gemini_session(cwd: str) -> Path | None:
    if not cwd:
        return None
    project_name = Path(cwd).name
    chats_dir = GEMINI_DIR / project_name / "chats"
    if not chats_dir.is_dir():
        return None
    files = list(chats_dir.glob("session-*.json"))
    if not files:
        return None
    return max(files, key=lambda path: session_mtime(path))


def find_session_for_harness(harness: str, cwd: str) -> Path | tuple[Path, str] | None:
    if harness == "claude":
        return find_claude_session(cwd)
    if harness == "codex":
        return find_codex_session(cwd)
    if harness == "gemini":
        return find_gemini_session(cwd)
    if harness == "opencode":
        return find_opencode_session(cwd)
    return None


def cwd_leaf(cwd: str | None) -> str | None:
    path = parse_cwd(cwd)
    trimmed = path.rstrip("/")
    if not trimmed:
        return None

    leaf = os.path.basename(trimmed)
    return leaf or None


def slugify(value: str | None) -> str | None:
    if not value:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or None


def next_available_name(base_name: str, taken: set[str]) -> str:
    if base_name not in taken:
        taken.add(base_name)
        return base_name

    suffix = 2
    while True:
        candidate = f"{base_name}{suffix}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate
        suffix += 1


def choose_launch_cmd(harness: str, snapshot: TtySnapshot | None) -> str:
    if snapshot is None:
        return DEFAULT_COMMANDS[harness]

    for command in snapshot.commands:
        if infer_harness(command) == harness:
            return command
        command_tokens = extract_command_tokens(command)
        if harness == "gemini" and command_tokens & NODE_WRAPPERS:
            return command

    if snapshot.foreground_command and infer_harness(snapshot.foreground_command) == harness:
        return snapshot.foreground_command

    return DEFAULT_COMMANDS[harness]


def detect_candidate(
    pane: dict[str, Any],
    adopted_pane_ids: set[int],
    taken_names: set[str],
) -> Candidate | None:
    pane_id = pane["pane_id"]
    if pane_id in adopted_pane_ids:
        return None

    title = pane.get("title") or ""
    tty_name = pane.get("tty_name")
    snapshot = inspect_tty_processes(tty_name)
    cwd_path = parse_cwd(pane.get("cwd"))

    best_match = None
    for harness in HARNESSES:
        title_match = harness in title.lower()
        proc_match = False
        if snapshot is not None:
            proc_match = any(
                hint in snapshot.tokens for hint in HARNESS_PROC_HINTS[harness]
            ) or any(infer_harness(command) == harness for command in snapshot.commands)
        if not proc_match and not title_match:
            continue

        session = find_session_for_harness(harness, cwd_path)
        score = 0
        reasons: list[str] = []
        if proc_match:
            score += 70
            reasons.append("proc")
        if session is not None:
            score += 40
            reasons.append("session")
        if title_match:
            score += 10
            reasons.append("title")

        match = {
            "harness": harness,
            "score": score,
            "source": "+".join(reasons),
            "session": session,
            "mtime": session_mtime(session),
        }
        if (
            best_match is None
            or match["score"] > best_match["score"]
            or (
                match["score"] == best_match["score"]
                and match["mtime"] > best_match["mtime"]
            )
        ):
            best_match = match

    if best_match is None:
        return None

    harness = best_match["harness"]
    source = best_match["source"]

    leaf = cwd_leaf(pane.get("cwd"))
    slug = slugify(leaf)
    if slug and slug != harness:
        base_name = f"{slug}_{harness}"
    else:
        base_name = harness
    proposed_name = next_available_name(base_name, taken_names)
    proposed_cmd = choose_launch_cmd(harness, snapshot)

    return Candidate(
        pane_id=pane_id,
        harness=harness,
        source=source,
        title=title,
        cwd=pane.get("cwd") or "",
        cwd_leaf=leaf,
        tty_name=tty_name,
        process_tokens=sorted(snapshot.tokens) if snapshot is not None else [],
        foreground_command=snapshot.foreground_command if snapshot is not None else None,
        session_hint=session_hint(best_match["session"]),
        proposed_name=proposed_name,
        proposed_cmd=proposed_cmd,
    )


def load_panes(args: argparse.Namespace) -> list[dict[str, Any]]:
    return run_json_command(cli_base(args) + ["list", "--format", "json"])


def load_agents(args: argparse.Namespace) -> list[dict[str, Any]]:
    return run_json_command(cli_base(args) + ["agent", "list", "--format", "json"])


def adopt_candidate(args: argparse.Namespace, candidate: Candidate) -> dict[str, Any]:
    cmd = cli_base(args) + [
        "agent",
        "adopt",
        "--pane-id",
        str(candidate.pane_id),
        "--name",
        candidate.proposed_name,
        "--cmd",
        candidate.proposed_cmd,
    ]
    parsed_cwd = parse_cwd(candidate.cwd)
    if parsed_cwd:
        cmd.extend(["--cwd", parsed_cwd])
    return run_json_command(cmd)


def render_candidates(candidates: list[Candidate]) -> None:
    if not candidates:
        print("No unadopted harness-like panes detected.")
        return

    print("Detected harness panes:")
    for candidate in candidates:
        print(
            f"  pane {candidate.pane_id}: {candidate.proposed_name}"
            f" [{candidate.harness}, via {candidate.source}]"
        )
        print(f"    cmd: {candidate.proposed_cmd}")
        if candidate.cwd:
            print(f"    cwd: {candidate.cwd}")
        if candidate.title:
            print(f"    title: {candidate.title}")
        if candidate.tty_name:
            print(f"    tty: {candidate.tty_name}")
        if candidate.foreground_command:
            print(f"    foreground: {candidate.foreground_command}")
        if candidate.session_hint:
            print(f"    session: {candidate.session_hint}")


def main() -> int:
    args = parse_args()

    try:
        panes = load_panes(args)
        agents = load_agents(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    adopted_pane_ids = {int(agent["pane_id"]) for agent in agents}
    taken_names = {str(agent["metadata"]["name"]) for agent in agents}

    requested_pane_ids = set(args.pane_id)
    candidates: list[Candidate] = []
    for pane in panes:
        if requested_pane_ids and int(pane["pane_id"]) not in requested_pane_ids:
            continue
        candidate = detect_candidate(pane, adopted_pane_ids, taken_names)
        if candidate is not None:
            candidates.append(candidate)

    if args.json and not args.apply:
        json.dump([asdict(candidate) for candidate in candidates], sys.stdout, indent=2)
        print()
        return 0

    if not args.apply:
        render_candidates(candidates)
        if candidates:
            print("\nRun with --apply to adopt them.")
        return 0

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for candidate in candidates:
        try:
            result = adopt_candidate(args, candidate)
            results.append(
                {
                    "pane_id": candidate.pane_id,
                    "name": candidate.proposed_name,
                    "harness": candidate.harness,
                    "source": candidate.source,
                    "result": result,
                }
            )
        except RuntimeError as exc:
            failures.append(
                {
                    "pane_id": candidate.pane_id,
                    "name": candidate.proposed_name,
                    "harness": candidate.harness,
                    "source": candidate.source,
                    "error": str(exc),
                }
            )

    if args.json:
        json.dump({"adopted": results, "failed": failures}, sys.stdout, indent=2)
        print()
    else:
        if results:
            print("Adopted panes:")
            for result in results:
                print(
                    f"  pane {result['pane_id']}: {result['name']}"
                    f" [{result['harness']}, via {result['source']}]"
                )
        if failures:
            print("Failed to adopt panes:", file=sys.stderr)
            for failure in failures:
                print(
                    f"  pane {failure['pane_id']}: {failure['name']}"
                    f" [{failure['harness']}] - {failure['error']}",
                    file=sys.stderr,
                )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
