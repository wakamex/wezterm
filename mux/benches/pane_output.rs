use async_trait::async_trait;
use chrono::{TimeZone, Utc};
use criterion::{black_box, criterion_group, criterion_main, BatchSize, Criterion, Throughput};
use mux::agent::{refresh_runtime_from_harness, AgentMetadata, AgentRuntimeSnapshot};
use mux::client::{ClientId, ClientViewId};
use mux::domain::{alloc_domain_id, Domain, DomainId, DomainState};
use mux::pane::{CachePolicy, ForEachPaneLogicalLine, Pane, PaneId, WithPaneLines};
use mux::renderable::{RenderableDimensions, StableCursorPosition};
use mux::tab::{SplitDirection, SplitRequest, SplitSize, Tab};
use mux::{Mux, MuxNotification, DEFAULT_WORKSPACE};
use parking_lot::{MappedMutexGuard, Mutex, MutexGuard};
use portable_pty::CommandBuilder;
use promise::spawn::SimpleExecutor;
use rangeset::RangeSet;
use std::io::Write;
use std::ops::Range;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use tempfile::TempDir;
use termwiz::hyperlink::Rule;
use termwiz::surface::{Line, SequenceNo};
use url::Url;
use wakterm_dynamic::Value;
use wakterm_term::color::ColorPalette;
use wakterm_term::{
    KeyCode, KeyModifiers, MouseEvent, Progress, SemanticZone, StableRowIndex, TerminalSize,
};

struct BenchPane {
    id: PaneId,
    size: Mutex<TerminalSize>,
    writer: Mutex<Vec<u8>>,
    domain_id: DomainId,
    title: String,
    cwd: Option<Url>,
    foreground_process_name: Option<String>,
}

impl BenchPane {
    fn new(id: PaneId, size: TerminalSize, domain_id: DomainId) -> Arc<dyn Pane> {
        Arc::new(Self {
            id,
            size: Mutex::new(size),
            writer: Mutex::new(Vec::new()),
            domain_id,
            title: String::new(),
            cwd: None,
            foreground_process_name: None,
        })
    }
}

#[async_trait(?Send)]
impl Pane for BenchPane {
    fn pane_id(&self) -> PaneId {
        self.id
    }

    fn get_cursor_position(&self) -> StableCursorPosition {
        unimplemented!()
    }

    fn get_current_seqno(&self) -> SequenceNo {
        0
    }

    fn get_metadata(&self) -> Value {
        Value::Null
    }

    fn get_changed_since(
        &self,
        _lines: Range<StableRowIndex>,
        _seqno: SequenceNo,
    ) -> RangeSet<StableRowIndex> {
        RangeSet::new()
    }

    fn get_lines(&self, _lines: Range<StableRowIndex>) -> (StableRowIndex, Vec<Line>) {
        (0, vec![])
    }

    fn with_lines_mut(&self, _lines: Range<StableRowIndex>, _with_lines: &mut dyn WithPaneLines) {}

    fn for_each_logical_line_in_stable_range_mut(
        &self,
        _lines: Range<StableRowIndex>,
        _for_line: &mut dyn ForEachPaneLogicalLine,
    ) {
    }

    fn get_logical_lines(&self, _lines: Range<StableRowIndex>) -> Vec<mux::pane::LogicalLine> {
        vec![]
    }

    fn apply_hyperlinks(&self, _lines: Range<StableRowIndex>, _rules: &[Rule]) {}

    fn get_dimensions(&self) -> RenderableDimensions {
        let size = self.size.lock();
        RenderableDimensions {
            cols: size.cols,
            viewport_rows: size.rows,
            scrollback_rows: size.rows,
            physical_top: 0,
            scrollback_top: 0,
            dpi: size.dpi,
            pixel_width: size.pixel_width,
            pixel_height: size.pixel_height,
            reverse_video: false,
        }
    }

    fn get_title(&self) -> String {
        self.title.clone()
    }

    fn get_progress(&self) -> Progress {
        Progress::None
    }

    fn send_paste(&self, _text: &str) -> anyhow::Result<()> {
        Ok(())
    }

    fn reader(&self) -> anyhow::Result<Option<Box<dyn std::io::Read + Send>>> {
        Ok(None)
    }

    fn writer(&self) -> MappedMutexGuard<'_, dyn Write> {
        MutexGuard::map(self.writer.lock(), |writer| writer as &mut dyn Write)
    }

    fn resize(&self, size: TerminalSize) -> anyhow::Result<()> {
        *self.size.lock() = size;
        Ok(())
    }

    fn key_down(&self, _key: KeyCode, _mods: KeyModifiers) -> anyhow::Result<()> {
        Ok(())
    }

    fn key_up(&self, _key: KeyCode, _mods: KeyModifiers) -> anyhow::Result<()> {
        Ok(())
    }

    fn mouse_event(&self, _event: MouseEvent) -> anyhow::Result<()> {
        Ok(())
    }

    fn perform_actions(&self, _actions: Vec<termwiz::escape::Action>) {}

    fn is_dead(&self) -> bool {
        false
    }

    fn palette(&self) -> ColorPalette {
        ColorPalette::default()
    }

    fn domain_id(&self) -> DomainId {
        self.domain_id
    }

    fn get_current_working_dir(&self, _policy: CachePolicy) -> Option<Url> {
        self.cwd.clone()
    }

    fn get_foreground_process_name(&self, _policy: CachePolicy) -> Option<String> {
        self.foreground_process_name.clone()
    }

    fn get_foreground_process_info(
        &self,
        _policy: CachePolicy,
    ) -> Option<procinfo::LocalProcessInfo> {
        None
    }

    fn can_close_without_prompting(&self, _reason: mux::pane::CloseReason) -> bool {
        true
    }

    fn has_unseen_output(&self) -> bool {
        false
    }

    fn is_mouse_grabbed(&self) -> bool {
        false
    }

    fn is_alt_screen_active(&self) -> bool {
        false
    }

    fn get_semantic_zones(&self) -> anyhow::Result<Vec<SemanticZone>> {
        Ok(vec![])
    }
}

struct BenchDomain {
    id: DomainId,
}

impl BenchDomain {
    fn new() -> Self {
        Self {
            id: alloc_domain_id(),
        }
    }
}

#[async_trait(?Send)]
impl Domain for BenchDomain {
    async fn spawn_pane(
        &self,
        size: TerminalSize,
        _command: Option<CommandBuilder>,
        _command_dir: Option<String>,
    ) -> anyhow::Result<Arc<dyn Pane>> {
        Ok(BenchPane::new(usize::MAX / 2, size, self.id))
    }

    fn detachable(&self) -> bool {
        false
    }

    fn domain_id(&self) -> DomainId {
        self.id
    }

    fn domain_name(&self) -> &str {
        "bench"
    }

    async fn attach(&self, _window_id: Option<mux::window::WindowId>) -> anyhow::Result<()> {
        Ok(())
    }

    fn detach(&self) -> Result<(), anyhow::Error> {
        Ok(())
    }

    fn state(&self) -> DomainState {
        DomainState::Attached
    }
}

struct BenchMuxGuard;

impl Drop for BenchMuxGuard {
    fn drop(&mut self) {
        Mux::shutdown();
    }
}

struct PaneOutputBench {
    _executor: SimpleExecutor,
    _guard: BenchMuxGuard,
    mux: Arc<Mux>,
    pane_id: PaneId,
}

struct InteractiveBench {
    _executor: SimpleExecutor,
    _guard: BenchMuxGuard,
    mux: Arc<Mux>,
    output_pane_id: PaneId,
    client_id: Arc<ClientId>,
}

struct CodexRefreshBench {
    _temp: TempDir,
    metadata: AgentMetadata,
    runtime: AgentRuntimeSnapshot,
    session_len: u64,
}

fn terminal_size() -> TerminalSize {
    TerminalSize {
        rows: 24,
        cols: 80,
        pixel_width: 800,
        pixel_height: 480,
        dpi: 96,
    }
}

fn sample_agent_metadata(name: &str) -> AgentMetadata {
    AgentMetadata {
        agent_id: format!("bench-agent-{name}"),
        name: name.to_string(),
        launch_cmd: "codex".to_string(),
        declared_cwd: format!("/tmp/{name}"),
        created_at: Utc.with_ymd_and_hms(2026, 3, 21, 12, 0, 0).unwrap(),
        repo_root: None,
        worktree: None,
        branch: None,
        managed_checkout: false,
    }
}

fn setup_pane_output_bench(adopted: bool) -> PaneOutputBench {
    config::use_test_configuration();
    let executor = SimpleExecutor::new();

    let domain = Arc::new(BenchDomain::new());
    let mux = Arc::new(Mux::new(Some(Arc::clone(&domain) as Arc<dyn Domain>)));
    Mux::set_mux(&mux);

    let size = terminal_size();
    let window_id = *mux.new_empty_window(Some(DEFAULT_WORKSPACE.to_string()), None);
    let tab = Arc::new(Tab::new(&size));
    let pane = BenchPane::new(10, size, domain.id);
    let pane_id = pane.pane_id();
    tab.assign_pane(&pane);
    mux.add_tab_and_active_pane(&tab).unwrap();
    mux.add_tab_to_window(&tab, window_id).unwrap();

    if adopted {
        mux.set_agent_metadata(pane_id, sample_agent_metadata("pane-output"))
            .unwrap();
    }

    PaneOutputBench {
        _executor: executor,
        _guard: BenchMuxGuard,
        mux,
        pane_id,
    }
}

fn setup_interactive_bench(with_subscriber: bool) -> InteractiveBench {
    config::use_test_configuration();
    let executor = SimpleExecutor::new();

    let domain = Arc::new(BenchDomain::new());
    let mux = Arc::new(Mux::new(Some(Arc::clone(&domain) as Arc<dyn Domain>)));
    Mux::set_mux(&mux);

    let size = terminal_size();
    let window_id = *mux.new_empty_window(Some(DEFAULT_WORKSPACE.to_string()), None);
    let tab = Arc::new(Tab::new(&size));

    let output_pane = BenchPane::new(20, size, domain.id);
    let output_pane_id = output_pane.pane_id();
    tab.assign_pane(&output_pane);

    let input_pane = BenchPane::new(21, size, domain.id);
    let input_pane_id = input_pane.pane_id();
    tab.split_and_insert(
        0,
        SplitRequest {
            direction: SplitDirection::Horizontal,
            target_is_second: true,
            size: SplitSize::Percent(50),
            top_level: false,
        },
        input_pane.clone(),
    )
    .unwrap();

    mux.add_tab_no_panes(&tab);
    mux.add_pane(&output_pane).unwrap();
    mux.add_pane(&input_pane).unwrap();
    mux.add_tab_to_window(&tab, window_id).unwrap();
    mux.set_agent_metadata(output_pane_id, sample_agent_metadata("interactive-output"))
        .unwrap();

    let client_id = Arc::new(ClientId::new());
    let view_id = Arc::new(ClientViewId("bench-interactive-view".to_string()));
    mux.register_client(client_id.clone(), view_id.clone());
    mux.set_active_tab_for_client_view(view_id.as_ref(), window_id, tab.tab_id())
        .unwrap();
    mux.set_active_pane_for_client_view(view_id.as_ref(), window_id, tab.tab_id(), input_pane_id)
        .unwrap();
    mux.record_focus_for_client(client_id.as_ref(), input_pane_id);

    if with_subscriber {
        let subscriber_mux = Arc::clone(&mux);
        let subscriber_client = client_id.clone();
        let hits = Arc::new(AtomicUsize::new(0));
        let hits_for_subscriber = hits.clone();
        mux.subscribe(move |notification| {
            match notification {
                MuxNotification::PaneOutput(pane_id) => {
                    let _ = subscriber_mux.resolve_pane_id(pane_id);
                    let _ = subscriber_mux.resolve_focused_pane(subscriber_client.as_ref());
                    hits_for_subscriber.fetch_add(1, Ordering::Relaxed);
                }
                MuxNotification::TabTitleChanged { tab_id, .. } => {
                    let _ = subscriber_mux.get_tab(tab_id);
                    hits_for_subscriber.fetch_add(1, Ordering::Relaxed);
                }
                _ => {}
            }
            true
        });
        black_box(hits);
    }

    InteractiveBench {
        _executor: executor,
        _guard: BenchMuxGuard,
        mux,
        output_pane_id,
        client_id,
    }
}

fn setup_codex_refresh_bench() -> CodexRefreshBench {
    let temp = TempDir::new().unwrap();
    let session = temp.path().join("rollout-bench.jsonl");
    let payload = concat!(
        "{\"payload\":{\"cwd\":\"/tmp/codex-bench\"}}\n",
        "{\"type\":\"event_msg\",\"timestamp\":\"2026-03-21T12:00:00Z\",\"payload\":{\"type\":\"task_started\",\"collaboration_mode_kind\":\"default\"}}\n",
        "{\"type\":\"event_msg\",\"timestamp\":\"2026-03-21T12:00:01Z\",\"payload\":{\"type\":\"agent_message\",\"phase\":\"commentary\"}}\n",
        "{\"type\":\"event_msg\",\"timestamp\":\"2026-03-21T12:00:02Z\",\"payload\":{\"type\":\"turn_context\",\"cwd\":\"/tmp/codex-bench\"}}\n",
        "{\"type\":\"event_msg\",\"timestamp\":\"2026-03-21T12:00:03Z\",\"payload\":{\"type\":\"agent_turn_complete\"}}\n"
    );
    std::fs::write(&session, payload).unwrap();

    let metadata = AgentMetadata {
        agent_id: "bench-codex-refresh".to_string(),
        name: "bench_codex".to_string(),
        launch_cmd: "codex".to_string(),
        declared_cwd: "/tmp/codex-bench".to_string(),
        created_at: Utc.with_ymd_and_hms(2026, 3, 21, 12, 0, 0).unwrap(),
        repo_root: None,
        worktree: None,
        branch: None,
        managed_checkout: false,
    };
    let mut runtime = AgentRuntimeSnapshot::new(&metadata);
    runtime.foreground_process_name = Some("/usr/bin/codex".to_string());
    runtime.session_path = Some(session.to_string_lossy().to_string());

    CodexRefreshBench {
        _temp: temp,
        metadata,
        runtime,
        session_len: payload.len() as u64,
    }
}

fn bench_pane_output(c: &mut Criterion) {
    let plain = setup_pane_output_bench(false);
    let adopted = setup_pane_output_bench(true);
    let interactive = setup_interactive_bench(false);
    let interactive_with_subscriber = setup_interactive_bench(true);

    let mut group = c.benchmark_group("pane_output");
    group.throughput(Throughput::Elements(1));
    group.bench_function("plain_pty", |b| {
        let mux = Arc::clone(&plain.mux);
        let pane_id = plain.pane_id;
        b.iter(|| mux.notify(MuxNotification::PaneOutput(black_box(pane_id))));
    });
    group.bench_function("adopted_metadata", |b| {
        let mux = Arc::clone(&adopted.mux);
        let pane_id = adopted.pane_id;
        b.iter(|| mux.notify(MuxNotification::PaneOutput(black_box(pane_id))));
    });
    group.bench_function("adopted_with_mux_subscriber", |b| {
        let mux = Arc::clone(&interactive_with_subscriber.mux);
        let pane_id = interactive_with_subscriber.output_pane_id;
        b.iter(|| mux.notify(MuxNotification::PaneOutput(black_box(pane_id))));
    });
    group.bench_function("interleaved_output_and_client_input", |b| {
        let mux = Arc::clone(&interactive.mux);
        let pane_id = interactive.output_pane_id;
        let client_id = interactive.client_id.clone();
        b.iter(|| {
            mux.notify(MuxNotification::PaneOutput(black_box(pane_id)));
            let _identity = mux.with_identity(Some(client_id.clone()));
            mux.record_input_for_current_identity();
        });
    });
    group.finish();
}

fn bench_agent_refresh(c: &mut Criterion) {
    let fixture = setup_codex_refresh_bench();

    let mut group = c.benchmark_group("agent_refresh");
    group.throughput(Throughput::Bytes(fixture.session_len));
    group.bench_function("codex_preferred_session", |b| {
        let metadata = fixture.metadata.clone();
        let runtime = fixture.runtime.clone();
        b.iter_batched(
            || runtime.clone(),
            |mut runtime| {
                refresh_runtime_from_harness(black_box(&mut runtime), black_box(&metadata));
                black_box(runtime);
            },
            BatchSize::SmallInput,
        );
    });
    group.finish();
}

criterion_group!(benches, bench_pane_output, bench_agent_refresh);
criterion_main!(benches);
