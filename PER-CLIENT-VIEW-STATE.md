# Per-Client View State

## Problem

Today, a mux window has one global active tab:

- `Window.active` in `mux/src/window.rs`
- the server exports that single choice in `ListPanesResponse.active_tabs`
- every attached client applies that same active tab during reconcile

That means two machines attached to the same shared window cannot look at
different tabs at the same time. Whichever side becomes authoritative next
causes the other side to switch.

This is the wrong ownership boundary.

Shared mux state should include:

- windows
- tabs
- pane trees
- PTY processes
- titles
- layout geometry

Client-local view state should include:

- which tab a given client is looking at in a window
- which pane a given client has focused in a tab
- later, possibly other purely presentational state

The long-term solution is to make that split explicit in both the mux model and
the protocol.

## Goals

- Multiple attached clients can share the same tabs and panes while selecting
  different active tabs in the same window.
- The solution works for both remote clients and a GUI running directly on the
  server host.
- The protocol is explicit. No inference from redraw timing or focus side
  effects.
- The design remains maintainable if we later move more state from "shared mux"
  to "client view".
- Spawn/split/activate actions use the active tab for the current client view,
  not some unrelated globally active tab.

## Non-Goals

- Duplicating tabs or windows per client
- Client-private layout trees
- Preserving per-client active tab forever with no stable client identity
- Backwards compatibility with the current fork protocol

## Current State

### Shared active tab

The current model stores active tab on the shared window object:

- `mux/src/window.rs`
- `mux/src/lib.rs:get_active_tab_for_window`

That value is treated as the active tab for every frontend.

### Server sync

The mux server includes one `active_tabs: HashMap<WindowId, TabId>` in
`ListPanesResponse`.

Current meaning:

- one active tab per window
- server-global, not client-specific

### Client reconcile

The remote client applies `active_tabs` directly to its local mirrored windows.

This is why one machine switching tabs flips the other machine too.

### Existing per-client precedent

The mux already has per-client state:

- `active_workspace`
- `focused_pane_id`

That proves the codebase already accepts "shared mux state plus client-local
state" as a valid model.

## Why A Small Patch Is Not Enough

There are two tempting shortcuts:

1. Stop syncing `active_tabs` from the server.
2. Infer active tab purely from the currently focused pane.

Both are insufficient.

### Not syncing global active tabs

That would reduce the symptom for remote mirrors, but it does not create a real
source of truth for per-client tab selection. Reconnects and reconciles would
still be ambiguous.

### Inferring from one focused pane

`focused_pane_id` is a single pane for the current client. That is not enough to
remember active tabs for multiple windows on that same client.

If a client has 3 windows open, each window needs its own remembered active tab.

## Proposed Model

Introduce a real per-client view-state layer.

### 1. Separate connection identity from view identity

Current `ClientId` is process-shaped and ephemeral:

- hostname
- username
- pid
- epoch
- in-process counter

That is useful for liveness and bookkeeping, but it is not a robust key for
client-local view state across reconnects.

Add a stable `ClientViewId`.

Properties:

- generated once per frontend instance/profile
- persisted locally by the GUI/client
- reused across reconnects
- distinct from the per-process connection id

This gives the server a stable key for "the MacBook view" versus "the desktop
view".

### 2. Add explicit per-window client view state

Add something like:

```rust
struct ClientWindowViewState {
    active_tab_id: Option<TabId>,
    active_pane_id: Option<PaneId>,
}
```

Store it per client view:

```rust
struct ClientInfo {
    connection_id: Arc<ClientId>,
    view_id: Arc<ClientViewId>,
    active_workspace: Option<String>,
    focused_pane_id: Option<PaneId>,
    window_view_state: HashMap<WindowId, ClientWindowViewState>,
}
```

Key point:

- `focused_pane_id` remains "currently focused pane overall"
- `window_view_state` becomes "what this client considers active in each window"

### 3. Keep global window active tab only as fallback

`Window.active` can remain for:

- headless/default behavior
- old code paths while refactoring
- session persistence of the shared window model

But GUI and attached-client behavior should stop treating it as the only truth.

When a current identity is available, active-tab resolution should come from the
client view state first.

## Protocol Changes

No compatibility constraints are needed here. Change the protocol cleanly and
bump the codec version.

### Replace global `active_tabs` with explicit client view state

`ListPanesResponse` should stop pretending that `active_tabs` is global shared
window state for all frontends.

Replace it with something like:

```rust
pub struct ClientWindowViewStateSnapshot {
    pub active_tab_id: Option<TabId>,
    pub active_pane_id: Option<PaneId>,
}

pub struct ListPanesResponse {
    pub tabs: Vec<PaneNode>,
    pub tab_titles: Vec<String>,
    pub window_titles: HashMap<WindowId, String>,
    pub client_window_view_state: HashMap<WindowId, ClientWindowViewStateSnapshot>,
}
```

Semantics:

- this snapshot is for the requesting client view only
- it is not "global server active tab"

### Add explicit client-view update PDUs

Do not rely on focus side effects alone.

Add explicit RPCs such as:

```rust
SetClientActiveTab {
    window_id: WindowId,
    tab_id: TabId,
}

SetClientActivePane {
    window_id: WindowId,
    tab_id: TabId,
    pane_id: PaneId,
}
```

`SetFocusedPane` can remain for liveness/input semantics, but it should not be
the only mechanism defining tab selection.

Explicit protocol is easier to reason about and test.

## Mux API Changes

### Identity-aware read path

Add new APIs and migrate GUI/client code to them:

- `get_active_tab_for_window_for_client(view_id, window_id)`
- `get_active_tab_for_window_for_current_identity(window_id)`
- `get_active_pane_for_window_for_current_identity(window_id)` if needed

The existing `get_active_tab_for_window(window_id)` should become:

- shared/global fallback
- not the normal GUI read path

### Identity-aware write path

Add:

- `set_active_tab_for_client_view(view_id, window_id, tab_id)`
- `set_active_tab_for_current_identity(window_id, tab_id)`

These should update per-client view state and emit a notification scoped to
frontends that need to repaint.

## Frontend Changes

### Remote client domain

Reconcile should apply `client_window_view_state` from the server, not global
active tabs.

That lets the MacBook and desktop mirrors stay different even while sharing the
same remote panes.

### GUI on the server host

This is the part that prevents the solution from being "just a remote-client
hack".

The local GUI must also participate as a first-class client view:

- it needs a stable `ClientViewId`
- tab switching must update that view state, not just `Window.active`
- active-tab reads in `TermWindow`, spawn logic, pane selection, tab bar, and
  commands must be identity-aware

If the server-host GUI keeps reading/writing only `Window.active`, it will still
fight with remote clients.

## Notifications

The current notification surface is centered around shared mux mutation.

For per-client view state, add an explicit notification such as:

```rust
MuxNotification::ClientWindowViewStateChanged {
    view_id: Arc<ClientViewId>,
    window_id: WindowId,
}
```

A frontend should ignore view-state notifications for other clients.

That keeps repaint traffic scoped and avoids cross-client churn.

## Session Persistence

Shared mux session persistence should continue to save:

- windows
- tabs
- panes
- shared titles
- shared geometry

Per-client view state should be persisted separately, if at all.

Recommended approach:

- do not mix per-client view state into shared `session.json`
- if persistence is desired, store it in a separate client-view-state file keyed
  by `ClientViewId`

That prevents the shared session file from becoming polluted by per-machine UI
preferences.

## Implementation Plan

### Phase 1: Data model and protocol

- Add `ClientViewId`
- Extend client registration/handshake to include it
- Add per-client `window_view_state`
- Add explicit `SetClientActiveTab` PDU
- Replace `ListPanesResponse.active_tabs` with client-specific view-state
  snapshot
- Bump codec version

### Phase 2: Identity-aware reads and writes

- Add identity-aware mux getters/setters
- Convert GUI tab switching to write per-client active tab
- Convert GUI active-tab reads to use per-client resolution
- Convert spawn/split context lookup to use per-client active tab

### Phase 3: Reconcile and notifications

- Apply client-specific view state in remote reconcile
- Add client-scoped notifications
- Make repaint/update paths ignore other clients' view notifications

### Phase 4: Cleanup

- Remove call sites that assume one global active tab for GUI behavior
- Restrict `Window.active` to fallback/shared semantics
- Update tests and docs

## Test Plan

### Unit tests

- per-client window view-state resolution with fallback to global window state
- switching tabs on client A does not change client B's active tab
- reconnect with the same `ClientViewId` restores prior per-window active tab
- reconnect with a different `ClientViewId` gets default fallback behavior

### Integration tests

- desktop and laptop attached to the same window select different tabs
- each client can spawn/split in its own selected tab without affecting the
  other
- local GUI and remote client stay independent
- reconnect/resync does not overwrite client-local tab choice with server-global
  tab choice

### Regression tests

- session restore still restores shared windows/tabs/panes correctly
- CLI actions that target explicit panes/windows still behave the same
- single-client behavior remains unchanged

## Risks

### Hidden assumption: active pane is also shared today

Active tab and active pane are related. A future cleanup may want to move more
of "selection/focus inside a tab" into per-client view state as well.

This design leaves room for that by creating a `ClientWindowViewState` struct
instead of adding yet another standalone map.

### CLI semantics

Some CLI paths currently rely on "the active tab for a window" without an
attached GUI identity. Those paths need explicit fallback rules:

- if there is a current client/view identity, use that
- otherwise use shared/global window active tab
- commands that accept explicit pane/window ids remain unambiguous

## Recommendation

Implement this as a real "per-client view state" feature, not as a narrower
"desynchronize active tab" tweak.

That means:

- stable client view identity
- explicit protocol
- identity-aware mux APIs
- local GUI and remote clients using the same model

Anything smaller will either break on reconnect, fail for the server-host GUI,
or turn into sync heuristics again.
