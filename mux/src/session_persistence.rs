//! Save and restore mux session state (tab layouts, CWDs, titles).
//!
//! On shutdown (or periodically), saves the current tab layout to a JSON
//! file. On startup, checks for the file and offers to restore.
//!
//! This is similar to tmux-resurrect: it saves the structure but not
//! terminal content. Processes must be relaunched.

use crate::tab::PaneNode;
use crate::Mux;
use anyhow::Context;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Saved state for one tab.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SavedTab {
    pub title: String,
    pub tree: PaneNode,
}

/// Saved state for one window (a window contains multiple tabs).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SavedWindow {
    pub workspace: String,
    pub tabs: Vec<SavedTab>,
}

/// Saved state for the entire mux session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SavedSession {
    pub version: u32,
    pub windows: Vec<SavedWindow>,
}

const SESSION_VERSION: u32 = 1;

fn session_path() -> PathBuf {
    config::RUNTIME_DIR.join("session.json")
}

/// Save the current mux session to disk.
pub fn save_session() -> anyhow::Result<PathBuf> {
    let mux = Mux::try_get().context("no mux instance")?;
    let mut windows = Vec::new();

    for window_id in mux.iter_windows() {
        if let Some(window) = mux.get_window(window_id) {
            let workspace = window.get_workspace().to_string();
            let mut tabs = Vec::new();
            for tab in window.iter() {
                let title = tab.get_title();
                let tree = tab.codec_pane_tree();
                tabs.push(SavedTab { title, tree });
            }
            if !tabs.is_empty() {
                windows.push(SavedWindow { workspace, tabs });
            }
        }
    }

    let session = SavedSession {
        version: SESSION_VERSION,
        windows,
    };

    let path = session_path();
    let json = serde_json::to_string_pretty(&session)
        .context("serializing session")?;

    std::fs::write(&path, &json)
        .with_context(|| format!("writing session to {}", path.display()))?;

    let total_tabs: usize = session.windows.iter().map(|w| w.tabs.len()).sum();
    log::info!(
        "Saved session: {} windows, {} tabs to {}",
        session.windows.len(),
        total_tabs,
        path.display(),
    );

    Ok(path)
}

/// Load a saved session from disk (if it exists).
pub fn load_session() -> anyhow::Result<Option<SavedSession>> {
    let path = session_path();
    if !path.exists() {
        return Ok(None);
    }

    let json = std::fs::read_to_string(&path)
        .with_context(|| format!("reading session from {}", path.display()))?;

    let session: SavedSession = serde_json::from_str(&json)
        .with_context(|| format!("parsing session from {}", path.display()))?;

    if session.version != SESSION_VERSION {
        log::warn!(
            "Session file version {} != expected {}, ignoring",
            session.version,
            SESSION_VERSION
        );
        return Ok(None);
    }

    let total_tabs: usize = session.windows.iter().map(|w| w.tabs.len()).sum();
    log::info!(
        "Loaded session: {} windows, {} tabs from {}",
        session.windows.len(),
        total_tabs,
        path.display(),
    );

    Ok(Some(session))
}

/// Remove the saved session file (after successful restore or on clean exit).
pub fn clear_session() -> anyhow::Result<()> {
    let path = session_path();
    if path.exists() {
        std::fs::remove_file(&path)
            .with_context(|| format!("removing session file {}", path.display()))?;
    }
    Ok(())
}
