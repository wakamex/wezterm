use crate::pane::PaneId;
use crate::tab::TabId;
use crate::window::WindowId;
use chrono::serde::ts_seconds;
use chrono::{DateTime, Utc};
use serde::*;
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::SystemTime;
use uuid::Uuid;

static CLIENT_ID: AtomicUsize = AtomicUsize::new(0);
lazy_static::lazy_static! {
    static ref EPOCH: u64 = SystemTime::now()
                                .duration_since(SystemTime::UNIX_EPOCH)
                                .unwrap().as_secs();
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, Hash)]
pub struct ClientId {
    pub hostname: String,
    pub username: String,
    pub pid: u32,
    pub epoch: u64,
    pub id: usize,
    pub ssh_auth_sock: Option<String>,
}

impl ClientId {
    pub fn new() -> Self {
        let id = CLIENT_ID.fetch_add(1, Ordering::Relaxed);
        Self {
            hostname: hostname::get()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|_| "localhost".to_string()),
            username: config::username_from_env().unwrap_or_else(|_| "somebody".to_string()),
            pid: unsafe { libc::getpid() as u32 },
            epoch: *EPOCH,
            id,
            ssh_auth_sock: crate::AgentProxy::default_ssh_auth_sock(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, Hash)]
pub struct ClientViewId(pub String);

impl ClientViewId {
    fn path() -> PathBuf {
        config::DATA_DIR.join("client-view-id")
    }

    pub fn persistent() -> Self {
        lazy_static::lazy_static! {
            static ref PERSISTENT_VIEW_ID: ClientViewId = ClientViewId::load_or_create();
        }
        PERSISTENT_VIEW_ID.clone()
    }

    fn load_or_create() -> Self {
        let path = Self::path();

        if let Ok(contents) = fs::read_to_string(&path) {
            let value = contents.trim();
            if !value.is_empty() {
                return Self(value.to_string());
            }
        }

        let view_id = Self(Uuid::new_v4().to_string());

        if let Some(parent) = path.parent() {
            if let Err(err) = fs::create_dir_all(parent) {
                log::warn!(
                    "unable to create parent directory for {}: {err:#}",
                    path.display()
                );
                return view_id;
            }
        }

        if let Err(err) = fs::write(&path, format!("{}\n", view_id.0)) {
            log::warn!("unable to persist {}: {err:#}", path.display());
        }

        view_id
    }
}

#[derive(Deserialize, Serialize, PartialEq, Eq, Debug, Clone, Default)]
pub struct ClientTabViewState {
    pub active_pane_id: Option<PaneId>,
}

#[derive(Deserialize, Serialize, PartialEq, Eq, Debug, Clone, Default)]
pub struct ClientWindowViewState {
    pub active_tab_id: Option<TabId>,
    pub last_active_tab_id: Option<TabId>,
    pub tabs: HashMap<TabId, ClientTabViewState>,
}

impl ClientWindowViewState {
    pub fn active_pane_id(&self) -> Option<PaneId> {
        let tab_id = self.active_tab_id?;
        self.tabs.get(&tab_id)?.active_pane_id
    }

    pub fn set_active_tab(&mut self, tab_id: TabId) {
        if self.active_tab_id != Some(tab_id) {
            self.last_active_tab_id = self.active_tab_id;
            self.active_tab_id = Some(tab_id);
        }
        self.tabs.entry(tab_id).or_default();
    }

    pub fn set_active_pane(&mut self, tab_id: TabId, pane_id: PaneId) {
        self.set_active_tab(tab_id);
        self.tabs.entry(tab_id).or_default().active_pane_id = Some(pane_id);
    }

    pub fn clear_removed_tab(&mut self, tab_id: TabId) {
        self.tabs.remove(&tab_id);
        if self.active_tab_id == Some(tab_id) {
            self.active_tab_id = None;
        }
        if self.last_active_tab_id == Some(tab_id) {
            self.last_active_tab_id = None;
        }
    }
}

#[derive(Deserialize, Serialize, PartialEq, Eq, Debug, Clone, Default)]
pub struct ClientViewState {
    pub windows: HashMap<WindowId, ClientWindowViewState>,
}

#[derive(Deserialize, Serialize, PartialEq, Debug, Clone)]
pub struct ClientInfo {
    pub client_id: Arc<ClientId>,
    pub view_id: Arc<ClientViewId>,
    /// The time this client last connected
    #[serde(with = "ts_seconds")]
    pub connected_at: DateTime<Utc>,
    /// Which workspace is active
    pub active_workspace: Option<String>,
    /// The last time we received input from this client
    #[serde(with = "ts_seconds")]
    pub last_input: DateTime<Utc>,
    /// The currently-focused pane
    pub focused_pane_id: Option<PaneId>,
}

impl ClientInfo {
    pub fn new(client_id: Arc<ClientId>, view_id: Arc<ClientViewId>) -> Self {
        Self {
            client_id,
            view_id,
            connected_at: Utc::now(),
            active_workspace: None,
            last_input: Utc::now(),
            focused_pane_id: None,
        }
    }

    pub fn update_last_input(&mut self) {
        self.last_input = Utc::now();
    }

    pub fn update_focused_pane(&mut self, pane_id: PaneId) {
        self.focused_pane_id.replace(pane_id);
    }
}
