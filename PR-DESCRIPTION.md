# PR: mux: reconcile split tree sizes after rebuild from pane sizes

## Summary

- Fix nested split pane sizes diverging after window resize on mux server
- Add `reconcile_tree_sizes()` — top-down constraint enforcement after `rebuild_splits_sizes_from_contained_panes()`
- Add `debug_assert_tree_invariants()` for debug builds
- 13 unit tests covering 6 layout patterns × multiple interleaving scenarios

## The Problem

When a client resizes its window, `apply_sizes_from_splits` calls `pane.resize()` on each leaf pane. For mux-connected panes, each `ClientPane::resize()` spawns an independent async task that sends a `Pdu::Resize` to the server. During rapid window resizing (dragging the edge), PDUs from different resize events interleave — some panes end up at sizes from event N while others are still at event N-1.

The server calls `rebuild_splits_sizes_from_contained_panes()` after each individual PDU, which reads whatever sizes panes currently report and replaces the tree node data wholesale. This locks in the inconsistency: a horizontal split's `first.rows` and `second.rows` can differ, and vertical sub-split children can overflow or underflow their parent's allocation.

```
Event 1 (80→90 rows): pane0=90, pane1=48, pane2=41
Event 2 (90→95 rows): pane0=95, pane1=51, pane2=43

PDU arrival order: E2.pane0, E2.pane1, E1.pane2(stale!)
Server final state: pane0=95, pane1=51, pane2=41
Right column: 51 + 1 + 41 = 93 ≠ 95 → UNDERFLOW by 2
```

This reproduces with a single client. Multiple clients make it worse.

## The Fix

`reconcile_tree_sizes()` — a top-down pass called after the bottom-up rebuild that enforces parent-child constraints at every split node:

- **Horizontal split**: `first.rows = second.rows = allocated.rows`; `second.cols = allocated.cols - 1 - first.cols`
- **Vertical split**: `first.cols = second.cols = allocated.cols`; `second.rows = allocated.rows - 1 - first.rows`

The first child's primary dimension is preserved, the second child absorbs the remainder. This matches the behavior of `apply_pane_size`.

Called from both `rebuild_splits_sizes_from_contained_panes()` (mux server path) and `TabInner::resize()` (local path, defensive).

## Tests

| Test | What it proves |
|------|---------------|
| `interleaved_pdus_break_pane_size_invariant` | Bug exists: raw pane sizes are inconsistent after PDU interleaving |
| `interleaved_pdus_break_column_width` | Bug exists: column width inconsistency from interleaved cols |
| `reconcile_fixes_interleaved_pdu_overflow` | Fix works: L-shaped layout, reconciliation restores invariants |
| `deep_nested_interleaved_pdus` | Fix works: 4-pane deep nesting (3 stacked in right column) |
| `t_shaped_interleaved_pdus` | Fix works: T-shaped layout (V-split with H-sub-split on top) |
| `grid_interleaved_pdus` | Fix works: 2x2 grid (H-split, both sides have V-sub-splits) |
| `first_pane_stale_interleaving` | Fix works: first pane stale (not last), L-shaped |
| `nested_split_normal_resize_preserves_invariants` | Regression: normal resize path stays correct |
| `all_layouts_resize_preserves_invariants` | Regression: L, T, deep nested, grid all survive resize cycles |
| `pane_removal_preserves_invariants` | Regression: removing panes from L, T, grid preserves invariants |
| `split_then_resize_preserves_invariants` | Regression: adding splits to nested layout then resizing is correct |

Without the fix: 6 tests fail. With the fix: all 13 pass.

## Test plan

- [x] `cargo test -p mux --lib tab::test` — 13 tests pass
- [x] Verified 6 tests fail without fix, proving they exercise the bug
- [x] `debug_assert_tree_invariants` active in debug builds catches violations at source
- [ ] Build fix branch and verify live violations drop to zero via `track-pane-sizes.py`
- [ ] Manual: resize window rapidly with nested splits, confirm no visual overflow

## Related issues

Fixes #6052, #5011, #4878, #5117

Related: #6885, #7540

🤖 Generated with [Claude Code](https://claude.com/claude-code)
