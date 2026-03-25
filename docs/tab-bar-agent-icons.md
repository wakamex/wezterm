# Tab Bar Agent Icons

## Goal

Show a small harness-specific icon beside the tab title for tabs whose active
pane is an agent pane.

Initial targets:

- Claude
- Codex
- Gemini
- OpenCode

This is a tab bar feature, not a tab title string feature.

## Why This Shape

The existing tab title pipeline is text-oriented:

- `wakterm-gui/src/termwindow/mod.rs` stores `TabInformation.tab_title` as a
  `String`
- `wakterm-gui/src/tabbar.rs` formats tab titles as text/`FormatItem`s
- image escape actions are ignored by the tab title parser

The fancy tab bar already uses the richer box-model render path and can render
sprites directly, so the icon should be implemented there instead of trying to
embed SVG or image data into the title string.

## Current Code Paths

Relevant files:

- `wakterm-gui/src/termwindow/mod.rs`
  - `TabInformation`
  - `get_tab_information()`
- `wakterm-gui/src/tabbar.rs`
  - `TabEntry`
  - `compute_tab_title()`
- `wakterm-gui/src/termwindow/render/fancy_tab_bar.rs`
  - fancy tab bar element construction
- `wakterm-gui/src/termwindow/box_model.rs`
  - sprite-capable box-model rendering
- `mux/src/agent.rs`
  - `AgentHarness`
- `mux/src/lib.rs`
  - agent metadata/runtime lookup by pane

## Data Model Plan

Add a lightweight icon hint to the GUI tab model.

### `TabInformation`

Extend `TabInformation` with something like:

```rust
pub harness_icon: Option<TabHarnessIcon>
```

Where `TabHarnessIcon` is a small GUI enum, for example:

```rust
enum TabHarnessIcon {
    Claude,
    Codex,
    Gemini,
    OpenCode,
}
```

This should also be exposed to Lua so `format-tab-title` can react to it if
needed, but the actual icon drawing should remain a native GUI responsibility.

### Source of Truth

Populate the icon hint from the active pane of the tab in
`TermWindow::get_tab_information()`.

Do not call `list_agents()` from the tab bar or paint path.

Instead, add or reuse a cheap cached mux getter that can answer:

- whether a pane is an agent pane
- which harness it belongs to

This lookup must only consult already-cached adopted/detected agent state and
must not trigger synchronous harness refresh work.

## Asset Strategy

### V1

Use packaged image assets, not runtime SVG parsing.

Reasons:

- simpler implementation
- no new SVG dependency in the render path
- the GUI already has PNG/image decoding and sprite atlas plumbing

Suggested asset location:

- `assets/tab-icons/`

Suggested files:

- `claude.png`
- `codex.png`
- `gemini.png`
- `opencode.png`

### Anthropic / Claude

For Claude, prefer the official icon asset from the local Anthropic brand kit:

- `/home/mihai/defi/anthropic_brand_kit.zip`
- `Anthropic media resources/Anthropic logos/Claude logos/4 Claude icon/SVG/ClaudeIcon-Rounded.svg`

For a small tab badge, use the icon asset, not the `Claude Code` wordmark.

### Branding / Shipping

For local experimentation, official assets are fine.

For public/upstream distribution, brand/trademark review should remain separate
from the implementation. If needed, start with internal placeholder/custom
assets and swap to official assets later.

## Rendering Plan

### V1 Scope

Render icons only in the fancy tab bar.

Do not change the classic text-only tab bar in the first iteration.

### `TabEntry`

Extend `TabEntry` in `wakterm-gui/src/tabbar.rs` with an optional icon field,
for example:

```rust
pub icon: Option<TabHarnessIcon>
```

Also reserve a fixed width for the icon when computing tab width and
truncation.

### Fancy Tab Bar

In `wakterm-gui/src/termwindow/render/fancy_tab_bar.rs`:

- load the icon as a sprite
- place it before the title text
- use a fixed compact size suitable for tabs
- keep spacing consistent whether the icon is present or absent

The box-model/sprite path already exists, so this should be implemented as a
sprite element rather than as terminal text cells.

### Fallback Behavior

If any of the following is true:

- no active pane
- active pane is not an agent
- no known harness
- asset missing
- tab is too narrow

then omit the icon and render the tab title normally.

## Caching Plan

Cache icon sprites by:

- icon kind
- scale / DPI bucket
- theme variant if needed

Do not decode or rasterize assets on every repaint.

Use the existing GUI image/sprite atlas infrastructure.

## Behavior Rules

- The icon reflects the active pane in the tab.
- Switching active panes in a split tab should update the icon.
- Reconnect/attach should restore the icon without requiring special user
  action.
- Window title behavior is unchanged.
- Pane title behavior is unchanged.

## Phasing

### Phase 1

- add `TabHarnessIcon`
- plumb icon hint into `TabInformation`
- render PNG-backed icons in fancy tab bar only

### Phase 2

- add classic tab bar support if desired

### Phase 3

- optionally switch from checked-in PNGs to SVG source + build-time or cached
  rasterization

### Phase 4

- optional Lua customization hooks for hiding/replacing icons

## Non-Goals

- inline SVG markup in tab titles
- arbitrary user-supplied SVG rendering in the title string path
- changing tab title strings themselves
- synchronous agent discovery/refresh in the paint path

## Open Questions

- Should the icon represent the active pane only, or should a tab with any
  agent pane show an icon even when a non-agent split is active?
- Should Claude use the generic Claude icon or a distinct Claude Code icon when
  the harness is specifically `Claude Code`?
- Do we want a config knob to disable icons globally?
- Do we want a Lua override for per-harness icon selection later?

## Done When

- Tabs with active Claude/Codex/Gemini/OpenCode panes show a small icon beside
  the title in the fancy tab bar.
- Switching panes in a split tab updates the icon correctly.
- Reconnect/attach restores icons correctly.
- Missing assets fail soft and do not break tab rendering.
- No tab bar render path performs synchronous agent refresh or `list_agents()`
  work.
