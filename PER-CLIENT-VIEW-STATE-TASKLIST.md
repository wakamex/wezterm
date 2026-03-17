# Per-Client View State Tasklist

- [x] Write long-term design in `PER-CLIENT-VIEW-STATE.md`
- [x] Add `ClientViewId` and persistent client-view generation
- [x] Extend client registration / handshake to carry `ClientViewId`
- [x] Add per-view mux state for active tab selection and per-tab active panes
- [x] Add explicit protocol updates for per-view active tab changes
- [x] Replace `ListPanesResponse.active_tabs` with client-specific view-state snapshot
- [x] Remove `Window.active` and shared active-tab APIs
- [x] Make mux active-tab reads identity-aware or explicit-target-only
- [x] Update remote reconcile to apply only requesting client's active tab state
- [x] Update local GUI tab switching and reads to use per-view active tabs
- [x] Update spawn/split and UI commands to use per-view active tab resolution
- [x] Update scripting / launcher / tab bar / title formatting paths
- [x] Update session persistence and layout snapshot logic to drop shared active-tab semantics
- [x] Add unit tests for client-view state and identity-aware active tab resolution
- [x] Add protocol and reconcile coverage
- [x] Add regression tests for GUI/client behavior and existing layout/resize flows
- [x] Run focused and broad test suites and fix breakages
