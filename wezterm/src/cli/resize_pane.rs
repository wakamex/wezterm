use clap::Parser;
use codec::Resize;
use mux::pane::PaneId;
use mux::tab::PaneNode;
use wezterm_client::client::Client;
use wezterm_term::TerminalSize;

#[derive(Debug, Parser, Clone)]
pub struct ResizePane {
    /// Specify the target pane.
    /// The default is to use the current pane based on the
    /// environment variable WEZTERM_PANE.
    #[arg(long)]
    pane_id: Option<PaneId>,

    /// Number of rows for the pane
    #[arg(long)]
    rows: usize,

    /// Number of columns for the pane
    #[arg(long)]
    cols: usize,
}

impl ResizePane {
    pub async fn run(&self, client: Client) -> anyhow::Result<()> {
        let pane_id = client.resolve_pane_id(self.pane_id).await?;

        // Resolve the containing tab_id from the pane list, since
        // Pdu::Resize requires it.
        let panes = client.list_panes().await?;
        let tab_id = find_tab_for_pane(&panes.tabs, pane_id)
            .ok_or_else(|| anyhow::anyhow!("pane {} not found in any tab", pane_id))?;

        client
            .resize(Resize {
                containing_tab_id: tab_id,
                pane_id,
                size: TerminalSize {
                    rows: self.rows,
                    cols: self.cols,
                    // Use zero for pixel dimensions — the server computes
                    // them from cell dimensions when needed.
                    pixel_width: 0,
                    pixel_height: 0,
                    dpi: 0,
                },
            })
            .await?;
        Ok(())
    }
}

fn find_tab_for_pane(tabs: &[PaneNode], target_pane_id: PaneId) -> Option<mux::tab::TabId> {
    for tab_root in tabs {
        if let Some((_, tab_id)) = find_pane_in_node(tab_root, target_pane_id) {
            return Some(tab_id);
        }
    }
    None
}

fn find_pane_in_node(
    node: &PaneNode,
    target: PaneId,
) -> Option<(mux::window::WindowId, mux::tab::TabId)> {
    match node {
        PaneNode::Empty => None,
        PaneNode::Leaf(entry) => {
            if entry.pane_id == target {
                Some((entry.window_id, entry.tab_id))
            } else {
                None
            }
        }
        PaneNode::Split { left, right, .. } => find_pane_in_node(left, target)
            .or_else(|| find_pane_in_node(right, target)),
    }
}
