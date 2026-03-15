#!/usr/bin/env python3
"""Generate HOTKEYS.md from wezterm source code.

Parses:
- config/src/keyassignment.rs for all KeyAssignment variants
- wezterm-gui/src/commands.rs for default key bindings

Compares fork vs upstream (fetches upstream file via git).

Usage:
    python3 generate-hotkeys.py > HOTKEYS.md
"""
import re
import subprocess
import sys


def get_file(path, ref=None):
    """Read a file from git ref or working tree."""
    if ref:
        try:
            return subprocess.check_output(
                ["git", "show", f"{ref}:{path}"],
                stderr=subprocess.DEVNULL,
            ).decode()
        except subprocess.CalledProcessError:
            return None
    with open(path) as f:
        return f.read()


def parse_key_assignments(content):
    """Extract all KeyAssignment variants from the enum definition."""
    m = re.search(r"pub enum KeyAssignment \{(.+?)\n\}", content, re.DOTALL)
    if not m:
        return []

    body = m.group(1)
    variants = []

    for line in body.split("\n"):
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        m = re.match(r"^(\w+)", line)
        if m and m.group(1)[0].isupper():
            variants.append(m.group(1))

    return sorted(set(variants))


def parse_command_defs(content):
    """Extract command definitions using a state machine parser.

    Returns dict: action_name -> {brief, keys: [(mods, key)]}
    """
    commands = {}

    # Find the function body
    func_start = content.find("fn derive_command_from_key_assignment")
    if func_start < 0:
        return commands

    # Extract from "Some(match action {" to the end of the function
    match_start = content.find("Some(match action {", func_start)
    if match_start < 0:
        return commands

    pos = match_start
    # Find each "=> CommandDef {" and parse the block
    while True:
        # Find next CommandDef
        idx = content.find("=> CommandDef {", pos)
        if idx < 0 or idx > len(content) - 100:
            break

        # Look backwards for the action name — find the last identifier
        # before "=>"
        preceding = content[max(0, idx - 500) : idx]
        # Find the match arm: text between the last "}" or "," and "=>"
        # The action name is typically the first identifier in the arm
        lines = preceding.rstrip().split("\n")

        # Walk backwards to find the arm start
        arm_text = ""
        for line in reversed(lines):
            arm_text = line.strip() + " " + arm_text
            # Arm starts after a }, or a , at the end of previous block
            if line.strip().endswith("},") or line.strip().endswith("},"):
                break
            if re.match(r"\s*\w+.*=>", line):
                break

        # Extract action name — first CamelCase identifier
        action = None
        for word in re.findall(r"\b([A-Z]\w+)\b", arm_text):
            if word not in (
                "CommandDef",
                "Modifiers",
                "Some",
                "None",
                "ClipboardCopyDestination",
                "ClipboardPasteSource",
                "ArgType",
                "ScrollbackEraseMode",
                "SelectionMode",
                "RotationDirection",
                "Pattern",
                "Cow",
                "String",
            ):
                action = word
                break

        if not action:
            pos = idx + 15
            continue

        # Parse the CommandDef block — find matching brace
        block_start = idx + len("=> CommandDef {")
        depth = 1
        block_pos = block_start
        while block_pos < len(content) and depth > 0:
            if content[block_pos] == "{":
                depth += 1
            elif content[block_pos] == "}":
                depth -= 1
            block_pos += 1
        block = content[block_start : block_pos - 1]

        # Extract brief (may span multiple lines with \ continuations)
        brief_m = re.search(r'brief:\s*"([^"]*(?:\\\n\s*[^"]*)*)"', block)
        brief = brief_m.group(1) if brief_m else ""
        brief = re.sub(r"\\\n\s*", " ", brief).strip()

        # Extract keys
        keys = []
        keys_m = re.search(r"keys:\s*vec!\[(.*?)\]", block, re.DOTALL)
        if keys_m:
            keys_str = keys_m.group(1)
            # Match both "Modifiers::A | Modifiers::B" and
            # "Modifiers::A.union(Modifiers::B)" styles
            for km in re.finditer(
                r'\(('
                r'Modifiers::\w+(?:\s*(?:\||\.\w+\()\s*Modifiers::\w+\)?)*'
                r')\s*,\s*"([^"]+)"',
                keys_str,
            ):
                mods_raw = km.group(1).replace(" ", "")
                # Normalize .union( to |
                mods_raw = re.sub(
                    r"\.union\(Modifiers::(\w+)\)", r"|Modifiers::\1", mods_raw
                )
                key = km.group(2)
                keys.append((mods_raw, key))

        commands[action] = {"brief": brief, "keys": keys}
        pos = block_pos


    return commands


def format_key_linux(mods_raw, key):
    """Format key for Linux (SUPER → Ctrl+Shift)."""
    parts = [m.strip() for m in mods_raw.split("|") if m.strip() != "NONE"]
    parts = [p.replace("Modifiers::", "") for p in parts]

    if "SUPER" in parts:
        parts.remove("SUPER")
        if "CTRL" not in parts:
            parts.append("CTRL")
        if "SHIFT" not in parts:
            parts.append("SHIFT")

    order = {"CTRL": 0, "SHIFT": 1, "ALT": 2}
    parts.sort(key=lambda x: order.get(x, 9))
    parts = [p for p in parts if p != "NONE"]

    mod_map = {"CTRL": "Ctrl", "SHIFT": "Shift", "ALT": "Alt"}
    formatted = [mod_map.get(m, m) for m in parts]
    if formatted:
        return "+".join(formatted) + "+" + key
    return key


def format_key_mac(mods_raw, key):
    """Format key for macOS (SUPER → Cmd)."""
    parts = [m.strip() for m in mods_raw.split("|")]
    parts = [p.replace("Modifiers::", "") for p in parts]
    parts = [p for p in parts if p != "NONE"]

    order = {"CTRL": 0, "SHIFT": 1, "ALT": 2, "SUPER": 3}
    parts.sort(key=lambda x: order.get(x, 9))

    mod_map = {"CTRL": "Ctrl", "SHIFT": "Shift", "ALT": "Opt", "SUPER": "Cmd"}
    formatted = [mod_map.get(m, m) for m in parts]
    if formatted:
        return "+".join(formatted) + "+" + key
    return key


def main():
    assignments_content = get_file("config/src/keyassignment.rs")
    commands_content = get_file("wezterm-gui/src/commands.rs")

    all_variants = parse_key_assignments(assignments_content)
    fork_commands = parse_command_defs(commands_content)

    # Parse upstream
    upstream_commands_content = get_file(
        "wezterm-gui/src/commands.rs", ref="upstream/main"
    )
    upstream_commands = (
        parse_command_defs(upstream_commands_content) if upstream_commands_content else {}
    )

    upstream_assignments_content = get_file(
        "config/src/keyassignment.rs", ref="upstream/main"
    )
    upstream_variants = (
        parse_key_assignments(upstream_assignments_content)
        if upstream_assignments_content
        else []
    )

    # Build output
    print("# WezTerm Hotkeys Reference")
    print()
    print(
        "Auto-generated from source. "
        "Run `python3 generate-hotkeys.py > HOTKEYS.md` to update."
    )
    print()

    # Separate into: has defaults vs no defaults
    with_keys = []
    without_keys = []

    for variant in all_variants:
        cmd = fork_commands.get(variant, {})
        keys = cmd.get("keys", [])
        if keys:
            with_keys.append(variant)
        else:
            without_keys.append(variant)

    print("## Default Key Bindings")
    print()
    print("| Action | Description | Linux/Win | macOS | Upstream |")
    print("|--------|-------------|-----------|-------|----------|")

    for variant in with_keys:
        cmd = fork_commands[variant]
        upstream_cmd = upstream_commands.get(variant, {})
        brief = cmd.get("brief", variant)
        keys = cmd["keys"]

        linux = ", ".join(format_key_linux(m, k) for m, k in keys)
        mac = ", ".join(format_key_mac(m, k) for m, k in keys)

        upstream_keys = upstream_cmd.get("keys", [])
        if keys == upstream_keys:
            up = "same"
        elif variant not in upstream_variants:
            up = "**fork only**"
        elif not upstream_keys:
            up = "changed"
        else:
            up_linux = ", ".join(format_key_linux(m, k) for m, k in upstream_keys)
            up = up_linux

        brief = brief.replace("|", "\\|")
        print(f"| `{variant}` | {brief} | {linux} | {mac} | {up} |")

    print()
    print("## Actions Without Default Bindings")
    print()
    print("These can be bound via `config.keys` in your wezterm config.")
    print()
    print("| Action | Description | Upstream |")
    print("|--------|-------------|----------|")

    for variant in without_keys:
        cmd = fork_commands.get(variant, {})
        brief = cmd.get("brief", "")
        if not brief:
            # Try to make a readable name from the variant
            brief = re.sub(r"([a-z])([A-Z])", r"\1 \2", variant)

        if variant not in upstream_variants:
            up = "**fork only**"
        else:
            up = "-"

        brief = brief.replace("|", "\\|")
        print(f"| `{variant}` | {brief} | {up} |")


if __name__ == "__main__":
    main()
