"""Stateful Gradio chat UI for OMEGA."""

from __future__ import annotations

import asyncio
import logging
import queue as stdlib_queue  # thread-safe stdlib queue — NOT asyncio.Queue
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from omega_agent import Config, OmegaAgent
from omega_agent.core.progress import RunProgress
from omega_agent.interaction.runner import InteractiveOmegaRunner
from omega_agent.interaction.session import OmegaChatSession
from omega_agent.interaction.types import InteractiveRunResult, InteractiveStatus

logger = logging.getLogger("omega_agent.ui.gradio")

try:
    import gradio as gr
except ImportError as e:
    raise ImportError(
        "Gradio is required for the OMEGA UI. Install with: pip install gradio>=4.0.0"
    ) from e

_UI_DIR = Path(__file__).resolve().parent
_neon_css_path    = _UI_DIR / "responsive_neon_v3.css"
_premium_css_path = _UI_DIR / "responsive_premium.css"
_standard_css_path= _UI_DIR / "responsive.css"
RESPONSIVE_CSS = (
    _neon_css_path.read_text(encoding="utf-8") if _neon_css_path.exists()
    else (_premium_css_path.read_text(encoding="utf-8") if _premium_css_path.exists()
          else _standard_css_path.read_text(encoding="utf-8"))
)


def _gradio_major_version() -> int:
    try:
        return int(gr.__version__.split(".")[0])
    except (ValueError, AttributeError):
        return 4


def _component_kwargs(component_cls, **kwargs: Any) -> Dict[str, Any]:
    import inspect
    try:
        params = inspect.signature(component_cls.__init__).parameters
    except (TypeError, ValueError):
        return kwargs
    allowed = set(params) - {"self"}
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in allowed}


def _blocks_context(**kwargs: Any):
    major = _gradio_major_version()
    blocks_kw = dict(kwargs)
    css = blocks_kw.pop("css", None)
    if major < 6 and css is not None:
        blocks_kw["css"] = css
    return gr.Blocks(**blocks_kw)


def _messages_for_chatbot(session: OmegaChatSession) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for msg in session.chat_messages:
        role    = msg.get("role", "user")
        content = msg.get("content", "")
        out.append({"role": role if role in ("user", "assistant") else "assistant",
                    "content": content})
    return out


def _deliverable_paths(agent_result: Optional[Any]) -> Tuple[Optional[str], Optional[str]]:
    if agent_result is None:
        return None, None
    meta         = getattr(agent_result, "metadata", None) or {}
    archive_path = meta.get("archive_path")
    project_root = meta.get("project_root")
    decision     = getattr(agent_result, "decision", None)
    if decision and getattr(decision, "risk_params", None):
        archive_path = archive_path or decision.risk_params.get("archive_path")
        project_root = project_root or decision.risk_params.get("project_root")
    output = getattr(agent_result, "output", "") or ""
    if not archive_path and output:
        m = re.search(r"\*\*Download zip:\*\* `([^`]+)`", output)
        if m:
            archive_path = m.group(1).strip()
    if not project_root and output:
        m = re.search(r"\*\*Project:\*\* `([^`]+)`", output)
        if m:
            project_root = m.group(1).strip()
    return archive_path, project_root


def _verify_display(agent_result: Optional[Any]) -> Tuple[str, str, str]:
    if agent_result is None:
        return "—", "—", ""
    meta   = getattr(agent_result, "metadata", None) or {}
    verify = meta.get("deliverable_verify") or {}
    if not verify and getattr(agent_result, "decision", None):
        rp = agent_result.decision.risk_params or {}
        if rp.get("build_verified") is True:
            return "Yes", str(rp.get("verify_attempts", "—")), ""
        if rp.get("verify_attempts"):
            return "No", str(rp.get("verify_attempts", 0)), ""
    if not verify:
        return "Not run (mock / no LLM)", "—", ""
    if verify.get("skip_reason") == "dag_verify_already_passed":
        return "Yes (DAG verify)", str(verify.get("verify_attempts", 1)), ""
    if verify.get("build_verified"):
        return "Yes", str(verify.get("verify_attempts", 0)), ""
    if verify.get("verify_attempts", 0) > 0:
        stderr = (verify.get("last_stderr") or verify.get("last_error") or "")[:1200]
        return "No", str(verify.get("verify_attempts", 0)), stderr
    return f"Skipped ({verify.get('skip_reason', 'skipped')})", "—", ""


def _downloads_dir(config: Optional[Config] = None) -> Path:
    cfg  = config or Config()
    path = Path(cfg.build_output_dir).resolve() / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_download_zip(archive_path: Optional[str],
                        config: Optional[Config] = None) -> Optional[str]:
    if not archive_path:
        return None
    for raw in [archive_path,
                str(archive_path).replace("/", "\\"),
                str(archive_path).replace("\\", "/")]:
        p = Path(raw)
        if p.is_file():
            src = p
            break
    else:
        return None
    dest_dir = _downloads_dir(config)
    dest     = dest_dir / src.name
    if dest.exists():
        try:
            if dest.stat().st_size == src.stat().st_size and dest.read_bytes() == src.read_bytes():
                return str(dest.resolve())
        except OSError:
            pass
        dest = dest_dir / f"{src.stem}-{int(time.time())}{src.suffix}"
    shutil.copy2(src, dest)
    return str(dest.resolve())


# ── Zip helpers ────────────────────────────────────────────────────────────────
# During streaming we MUST return gr.update() — never gr.File()/gr.DownloadButton()
# instances.  Component instances cause Gradio to buffer ALL yields and only flush
# them to the browser when the generator finishes (the original delay bug).

def _zip_hidden() -> Tuple[Any, Any, Any]:
    return (
        gr.update(value=None, visible=False),
        gr.update(value=None, visible=False),
        gr.update(value="",   visible=False),
    )


def _zip_final(archive_path: Optional[str],
               config: Optional[Config] = None) -> Tuple[Any, Any, Any]:
    zp = _stage_download_zip(archive_path, config) if archive_path else None
    if not zp:
        return _zip_hidden()
    name = Path(zp).name
    return (
        gr.update(value=zp,  visible=True, label=f"Project zip — {name}"),
        gr.update(value=zp,  visible=True),
        gr.update(value=f"**Project zip ready:** `{name}`", visible=True),
    )


# ── Output tuple builders ──────────────────────────────────────────────────────
# Gradio 6 streams reliably when the generator updates a SMALL output set with
# plain Python values. Updating 16 outputs (File/Markdown + gr.update) per tick
# drops SSE chunks in the browser — backend runs, UI stays at 0% / placeholder.

def _pack_stream(
    session: OmegaChatSession,
    log: str,
    pct: int,
    status_msg: str,
    *,
    awaiting: str = "No",
) -> tuple:
    """6-tuple for SIDEBAR_STREAM_OUTPUTS during generator streaming."""
    return (
        _messages_for_chatbot(session),
        session.to_state_dict(),
        status_msg,
        awaiting,
        log,
        pct,
    )


def _pack_deliverable_panel(
    session_state: Optional[Dict[str, Any]],
    config: Config,
) -> tuple:
    """10-tuple for DELIVERABLE_OUTPUTS (after run or on reset)."""
    session = OmegaChatSession.from_state_dict(session_state)
    agent_result = session.agent_result
    domain = agent_result.domain if agent_result else "—"
    quality = "—"
    if agent_result and agent_result.metadata:
        qs = agent_result.metadata.get("quality_score")
        if qs is not None:
            quality = f"{float(qs)*100:.0f}%"
    latency = f"{agent_result.latency:.1f}s" if agent_result else "—"
    build_ok, verify_att, verify_err = _verify_display(agent_result)
    arch, proj = _deliverable_paths(agent_result)
    zf, zb, zh = _zip_final(arch, config)
    return (
        domain,
        quality,
        latency,
        build_ok,
        verify_att,
        verify_err,
        zf,
        zb,
        zh,
        proj or "—",
    )


def _pack_reset_all(session: OmegaChatSession, config: Config) -> tuple:
    """Full 16-tuple for New session (non-streaming)."""
    zf, zb, zh = _zip_hidden()
    return (
        [],
        session.to_state_dict(),
        _status_label(InteractiveStatus.IDLE),
        "No",
        "—",
        "—",
        "—",
        "—",
        "—",
        "",
        "",
        0,
        zf,
        zb,
        zh,
        "—",
    )


def _status_label(status: InteractiveStatus,
                  request_key: Optional[str] = None) -> str:
    return {
        InteractiveStatus.IDLE:           "Ready — describe your automation goal.",
        InteractiveStatus.RUNNING:        "Running workflow…",
        InteractiveStatus.AWAITING_INPUT: f"Waiting for you: `{request_key or 'input'}`",
        InteractiveStatus.COMPLETED:      "Workflow completed.",
        InteractiveStatus.FAILED:         "Workflow failed — send a new goal.",
    }.get(status, str(status.value))


# ── Thread-safe progress bridge ────────────────────────────────────────────────
# Gradio MAY run async generators in a separate thread with its own event loop.
# asyncio.Queue is NOT thread-safe across different event loops.
# We use stdlib threading.Queue which is always safe across threads/loops.

class _ThreadSafeProgress(RunProgress):
    """RunProgress subclass that pushes events to a threading.Queue."""

    def __init__(self) -> None:
        super().__init__()
        self._tqueue: stdlib_queue.Queue = stdlib_queue.Queue()

    def checkpoint(self, phase: str, message: str, fraction: float, detail: str = "") -> None:
        # Call parent to update fraction/message/lines
        super().checkpoint(phase, message, fraction, detail)
        # Push to thread-safe queue (works regardless of which event loop is running)
        try:
            self._tqueue.put_nowait({
                "fraction": self.fraction,
                "message":  message,
                "log":      self.format_log(),
                "phase":    phase,
                "done":     False,
            })
        except stdlib_queue.Full:
            pass

    def mark_done(self) -> None:
        self._tqueue.put_nowait({"done": True})

    def get_nowait(self) -> Optional[Dict[str, Any]]:
        try:
            return self._tqueue.get_nowait()
        except stdlib_queue.Empty:
            return None


# ── Main app class ─────────────────────────────────────────────────────────────

class GradioOmegaApp:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.runner = InteractiveOmegaRunner(
            agent=OmegaAgent(config=self.config),
            config=self.config,
        )
        self._tenant_id = self.config.default_tenant_id

    def _chat_stream(
        self,
        message: str,
        history: List[Dict[str, str]],
        session_state: Optional[Dict[str, Any]],
        max_time: int,
    ):
        """
        SYNCHRONOUS generator — Gradio streams sync generators reliably on all
        versions (3.x / 4.x / 5.x / 6.x) without any event-loop complications.

        The agent coroutine runs in a background thread via threading.Thread +
        asyncio.run(), while the generator polls a threading.Queue for progress
        events.  threading.Queue is safe across threads and event loops.
        """
        session = OmegaChatSession.from_state_dict(session_state)
        session.metadata.setdefault("tenant_id", self._tenant_id)

        progress    = _ThreadSafeProgress()
        result_box: Dict[str, Any] = {"result": None, "error": None}

        # ── STEP 1: yield startup state IMMEDIATELY ───────────────────────
        startup_log = (
            ">> OMEGA ORCHESTRATION ENGINE ACTIVATED\n"
            "-> Initializing AI reasoning system...\n"
            "-> Loading execution models and components...\n"
            "-> Preparing automation workspace...\n"
            "-> Connecting to execution queue...\n"
            "-> Standing by for workflow analysis..."
        )
        yield _pack_stream(session, startup_log, 1, "Starting OMEGA…")

        # ── STEP 2: run agent in background thread ────────────────────────
        def _run_in_thread() -> None:
            try:
                result_box["result"] = asyncio.run(
                    self.runner.handle_message(
                        message,
                        session=session,
                        max_time=max_time,
                        progress=progress,
                    )
                )
            except Exception as exc:
                result_box["error"] = exc
            finally:
                progress.mark_done()

        thread = threading.Thread(target=_run_in_thread, daemon=True)
        thread.start()

        # ── STEP 3: poll threading.Queue and yield each event ─────────────
        accumulated_log = startup_log
        pct             = 1

        while True:
            time.sleep(0.15)  # poll interval — 150 ms gives smooth updates

            # Drain ALL available events from queue in one pass
            new_events: List[Dict[str, Any]] = []
            while True:
                evt = progress.get_nowait()
                if evt is None:
                    break
                new_events.append(evt)

            done = False
            for evt in new_events:
                if evt.get("done"):
                    done = True
                    break
                new_log = evt.get("log", "").strip()
                if new_log:
                    accumulated_log = new_log
                else:
                    accumulated_log += f"\n-> {evt.get('message', 'processing')}..."
                pct = min(99, int(evt["fraction"] * 100))

            status_msg = f"Running ({pct}%) — {progress.message}"
            yield _pack_stream(session, accumulated_log, pct, status_msg)

            if done:
                break

        thread.join(timeout=5)

        # ── STEP 4: final sidebar yield (deliverable panel via .then()) ─────
        if result_box["error"]:
            raise result_box["error"]

        result = result_box["result"]
        final_log = progress.format_log() or accumulated_log
        final_pct = 100 if (result and result.status == InteractiveStatus.COMPLETED) else pct
        status = _status_label(
            result.status if result else InteractiveStatus.IDLE,
            result.request.key if (result and result.request) else None,
        )
        awaiting = "Yes — reply in the chat." if (result and result.needs_input) else "No"
        yield _pack_stream(session, final_log, final_pct, status, awaiting=awaiting)

    def reset_session(self):
        """Synchronous generator for the reset button."""
        session = OmegaChatSession()
        session.metadata["tenant_id"] = self._tenant_id
        yield _pack_reset_all(session, self.config)


# ── Gradio layout ──────────────────────────────────────────────────────────────

def build_demo(config: Optional[Config] = None) -> "gr.Blocks":
    cfg = config or Config()
    app = GradioOmegaApp(config=cfg)

    with _blocks_context(
        title="OMEGA — Interactive Automation",
        css=RESPONSIVE_CSS,
        elem_id="omega-app-root",
    ) as demo:
        gr.Markdown(
            """
<div class="omega-hero">OMEGA</div>

**AI-Powered Automation Orchestration Engine**

Describe your automation goal. OMEGA will **reason → plan → execute → iterate** until complete. Watch real-time logs as AI agents work.

🚀 **Fully Responsive** | ⚡ **Real-Time Updates** | 🎯 **AI-Driven Execution**
            """,
            elem_classes=["omega-intro"],
        )

        session_state = gr.State(value=None)

        with gr.Row(elem_classes=["omega-layout-row"]):
            # ── LEFT ────────────────────────────────────────────────────────
            with gr.Column(scale=3, elem_classes=["omega-chat-column"]):
                chatbot = gr.Chatbot(
                    **_component_kwargs(
                        gr.Chatbot,
                        label="Conversation",
                        height=420,
                        show_copy_button=True,
                    )
                )
                with gr.Row(elem_classes=["omega-input-row"]):
                    msg = gr.Textbox(
                        label="Message",
                        placeholder="e.g. Build a React app with tests…",
                        scale=4, lines=2, max_lines=6,
                    )
                    send = gr.Button("Send", variant="primary", scale=1, min_width=88)
                with gr.Row(elem_classes=["omega-actions"]):
                    clear = gr.Button("New session", variant="secondary")

            # ── RIGHT ───────────────────────────────────────────────────────
            with gr.Column(scale=1, elem_classes=["omega-side-column"]):
                gr.Markdown("### Session")
                status_box = gr.Textbox(
                    label="Status", interactive=False, lines=1, max_lines=2
                )
                progress_bar = gr.Slider(
                    minimum=0, maximum=100, value=0, step=1,
                    label="Progress %", interactive=False,
                )
                progress_log = gr.Textbox(
                    label="Execution log", interactive=False,
                    lines=5, max_lines=8,
                    placeholder="Live logs appear here…",
                )
                awaiting_box = gr.Textbox(
                    label="Awaiting input?", interactive=False, lines=1, max_lines=1
                )
                max_time = gr.Slider(
                    minimum=120, maximum=3600, value=600, step=60,
                    label="Max runtime (s)",
                )
                gr.Markdown("*Build tasks can take 5–10 min per attempt.*")

                gr.Markdown("### Last run")
                domain_box         = gr.Textbox(label="Domain",          interactive=False, lines=1, max_lines=1)
                quality_box        = gr.Textbox(label="Quality",         interactive=False, lines=1, max_lines=1)
                latency_box        = gr.Textbox(label="Latency",         interactive=False, lines=1, max_lines=1)
                build_verified_box = gr.Textbox(label="Build verified",  interactive=False, lines=1, max_lines=1)
                verify_attempts_box= gr.Textbox(label="Verify attempts", interactive=False, lines=1, max_lines=1)
                verify_stderr_box  = gr.Textbox(label="Last verify error",interactive=False, lines=2, max_lines=3)
                project_box        = gr.Textbox(label="Project folder",  interactive=False, lines=1, max_lines=2)

                gr.Markdown("### Deliverable")
                zip_link     = gr.Markdown(visible=False)
                zip_file     = gr.File(label="Project zip", visible=False, interactive=False, type="filepath")
                zip_download = gr.DownloadButton("⬇ Download zip", variant="secondary", visible=False)
                gr.Markdown("*Credential keys → paste in chat. Saved to `omega_vault.json`.*")

        # Full layout order (reset / reference)
        outputs = [
            chatbot,             # 0
            session_state,       # 1
            status_box,          # 2
            awaiting_box,        # 3
            domain_box,          # 4
            quality_box,         # 5
            latency_box,         # 6
            build_verified_box,  # 7
            verify_attempts_box, # 8
            verify_stderr_box,   # 9
            progress_log,        # 10
            progress_bar,        # 11
            zip_file,            # 12
            zip_download,        # 13
            zip_link,            # 14
            project_box,         # 15
        ]

        # Generator only touches these — plain values, no File/Markdown per tick
        sidebar_stream_outputs = [
            chatbot,
            session_state,
            status_box,
            awaiting_box,
            progress_log,
            progress_bar,
        ]
        deliverable_outputs = [
            domain_box,
            quality_box,
            latency_box,
            build_verified_box,
            verify_attempts_box,
            verify_stderr_box,
            zip_file,
            zip_download,
            zip_link,
            project_box,
        ]

        chat_inputs = [msg, chatbot, session_state, max_time]

        def _refresh_deliverable(session_state: Optional[Dict[str, Any]]):
            return _pack_deliverable_panel(session_state, cfg)

        # Timer on log only; do not cover status/slider (Gradio 6 "full" bug)
        _stream_kw = dict(
            show_progress="minimal",
            show_progress_on=progress_log,
        )

        send.click(
            fn=app._chat_stream,
            inputs=chat_inputs,
            outputs=sidebar_stream_outputs,
            **_stream_kw,
        ).then(lambda: "", outputs=msg).then(
            _refresh_deliverable,
            inputs=[session_state],
            outputs=deliverable_outputs,
        )
        msg.submit(
            fn=app._chat_stream,
            inputs=chat_inputs,
            outputs=sidebar_stream_outputs,
            **_stream_kw,
        ).then(lambda: "", outputs=msg).then(
            _refresh_deliverable,
            inputs=[session_state],
            outputs=deliverable_outputs,
        )
        clear.click(fn=app.reset_session, outputs=outputs)

    return demo


def launch_ui(
    config: Optional[Config] = None,
    share: bool = False,
    server_name: str = "0.0.0.0",
    server_port: int = 7860,
    **kwargs: Any,
) -> None:
    cfg  = config or Config()
    demo = build_demo(config=cfg)
    demo.queue(default_concurrency_limit=max(1, cfg.gradio_concurrency))
    launch_kw: Dict[str, Any] = dict(
        server_name=server_name,
        server_port=server_port,
        share=share,
        show_error=True,
        **kwargs,
    )
    if _gradio_major_version() >= 6:
        launch_kw.setdefault("css",   RESPONSIVE_CSS)
        launch_kw.setdefault("theme", gr.themes.Soft())
    ws        = Path(cfg.workspace_root).resolve()
    out       = Path(cfg.build_output_dir).resolve()
    downloads = out / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    allowed = [str(ws), str(out), str(downloads), str(Path.cwd().resolve())]
    if hasattr(gr, "set_static_paths"):
        gr.set_static_paths(paths=[ws, out, downloads])
    launch_kw.setdefault("allowed_paths", allowed)
    try:
        demo.launch(**launch_kw)
    except TypeError:
        launch_kw.pop("theme", None)
        demo.launch(**launch_kw)


if __name__ == "__main__":
    launch_ui()
