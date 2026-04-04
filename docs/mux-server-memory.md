# Mux Server Memory Usage

Tracking memory growth in `wakterm-mux-server` for long-running sessions.

## Observed behavior

On 2026-04-04, a `wakterm-mux-server` process running for ~1 week (since Mar 27)
with 13 tabs was OOM-killed on a Linux (Fedora) host:

```
wakterm-mux-server.service: A process of this unit has been killed by the OOM killer.
wakterm-mux-server.service: Failed with result 'oom-kill'.
Consumed 1w 15h 46min CPU time, 25.5G memory peak, 64.1G memory swap peak.
```

Session persistence saved successfully before death, and the new server restored
all 13 tabs on restart.

## Upstream reports

This is a known problem in upstream wezterm:

- **[wezterm#7363](https://github.com/wezterm/wezterm/issues/7363)** — "Wezterm using 22 GB of RAM?" with built-in mux server. Still open.
- **[wezterm#1342](https://github.com/wezterm/wezterm/issues/1342)** — Proposal for disk-backed scrollback with zstd compression. Never implemented.

Previously fixed upstream issues that reduced memory but didn't eliminate the fundamental problem:

- **[wezterm#2453](https://github.com/wezterm/wezterm/issues/2453)** — Oversized LRU caches (2.2 GB -> 150 MB). Fixed 2022.
- **[wezterm#1626](https://github.com/wez/wezterm/issues/1626)** — Clustered line storage with attribute compression (2.1 GB -> 620 KB for 1M lines). Fixed 2022.
- **[wezterm#6003](https://github.com/wezterm/wezterm/issues/6003)** — Pre-allocated scrollback for absurd `scrollback_lines` values. Fixed by capping max.

## Confirmed causes

### 1. Unbounded action accumulation in SynchronizedOutput mode (FIXED)

**Location:** `mux/src/lib.rs`, `parse_buffered_data()`

When a terminal application enables SynchronizedOutput (`CSI?2026h`), parsed
actions accumulate in a `Vec<Action>` that was only flushed when the mode was
reset. If an application got stuck in this mode (crash, hang, or generates
large amounts of output while in it), memory grew without bound.

**Confirmed by tests:**
- `synchronized_output_accumulates_unbounded_actions` — 1MB of data during
  hold accumulates >500KB in the buffer, flushed on reset.
- `synchronized_output_capped_at_4mb` — 8MB of data during hold stays under
  5MB thanks to the safety valve.
- `normal_output_flushes_actions_promptly` — control test showing normal
  mode flushes promptly.

**Fix:** Added a 4MB safety valve. When the action buffer exceeds 4MB during
SynchronizedOutput hold, it is force-flushed with a warning log. This may
cause a partial frame to render, but prevents unbounded memory growth. A
well-behaved TUI frame is typically under 100KB, so 4MB is generous.

### 2. Unbounded LRU cache after resize

**Location:** `wakterm-client/src/pane/renderable.rs`, `make_all_stale()` (~line 427)

On every pane resize or palette change, `make_all_stale()` replaces the bounded
LRU line cache with `LruCache::unbounded()`. The original bound
(`scrollback_lines.max(128)`) is never restored. Over time, this cache can grow
well past its intended size.

### 3. Scrollback held entirely in memory

**Location:** `term/src/screen.rs`

Each pane's scrollback is a `VecDeque<Line>` with no disk-backed eviction.
With default `scrollback_lines = 3500`, 13 tabs at ~70 KB/line = ~3 GB baseline.
Lines containing embedded images (`Arc<ImageData>`) can be much larger and are
not cleaned up when scrolled out of view.

### 4. Image data retained via Arc references

Sixel, iTerm2, and Kitty image data is stored as `Arc<ImageData>` in the
terminal state image cache (16 entries). However, scrollback lines hold their
own Arc references to image data, so eviction from the cache doesn't free the
data until the line itself is dropped.

## Investigation plan

### Step 1: Instrument the mux server (DONE)

Added `mux::memory_report` module. Every 60 seconds (piggybacking on the
session persistence tick), the mux server logs:

- Process RSS (from `/proc/self/statm` on Linux)
- Total pane count and scrollback rows
- Per-pane action buffer bytes (for any pane with a non-zero buffer)

Each pane's reader thread registers an `AtomicUsize` gauge in the global
`ACTION_BUFFER_SIZES` map, updated after every parse iteration.

Example output at `WAKTERM_LOG=info`:
```
memory: RSS 1.2G | 13 panes, 45500 total scrollback rows, 0B buffered
```

### Step 2: Synthetic reproduction tests (DONE)

Three unit tests in `mux/src/lib.rs` that drive `parse_buffered_data` directly
via a socketpair:

1. **`synchronized_output_accumulates_unbounded_actions`** — Sends `CSI?2026h`
   then 1MB of output. Verifies buffer accumulates >500KB while held, then
   flushes to near-zero on `CSI?2026l`. Confirmed the OOM mechanism.

2. **`synchronized_output_capped_at_4mb`** — Sends 8MB during hold. Verifies
   the safety valve keeps the buffer under 5MB.

3. **`normal_output_flushes_actions_promptly`** — Control test: 1MB without
   SynchronizedOutput. Buffer stays small.

### Step 3: Fix and verify (DONE)

Added 4MB safety valve in `parse_buffered_data`. Force-flushes the action
buffer when it exceeds 4MB during SynchronizedOutput hold. Logs a warning
when triggered. Verified by `synchronized_output_capped_at_4mb` test.

## Remaining work

### Done

1. **Cap the actions buffer in SynchronizedOutput mode.** Force-flush at 4MB.
2. **Add memory monitoring to the mux server.** 60s RSS + per-pane reporting.

### Still open

3. **Preserve LRU bound in `make_all_stale()`.** Create the new cache with the
   same capacity as the old one instead of using `unbounded()`. This affects
   the GUI client, not the mux server, so it didn't cause this OOM — but it's
   still a bug worth fixing.

4. **Drop image data from old scrollback lines.** When a line scrolls past a
   certain age or distance from the viewport, release its image attachments.

5. **Disk-backed scrollback.** Implement the architecture from wezterm#1342:
   segmented storage with zstd compression, written to disk, with an LRU
   in-memory window. This is the real fix but is a significant effort.
