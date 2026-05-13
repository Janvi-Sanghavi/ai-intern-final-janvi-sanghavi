"""
ui.py
-----
Gradio frontend for the AI Research Assistant.

Improvements over v2:
  • Modern AI SaaS color palette (Perplexity / Linear / Notion AI aesthetic)
  • Polished hero section with subtitle and feature list
  • Topic suggestion chips that autofill the input
  • Improved empty states with onboarding guidance
  • Renamed sidebar to "Recent Research Reports"
  • Lightweight progress status messages per pipeline stage
  • Modern footer
  • No global mutable state — uses gr.State for per-session data
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import gradio as gr

from agent import ResearchAgent, ResearchResult

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Singleton agent (shared across sessions — stateless by design)
# ---------------------------------------------------------------------------
try:
    _agent = ResearchAgent()
    _agent_error = ""
except EnvironmentError as exc:
    _agent = None          # type: ignore[assignment]
    _agent_error = str(exc)

# ---------------------------------------------------------------------------
# Suggestion chips
# ---------------------------------------------------------------------------
TOPIC_SUGGESTIONS = [
    "Artificial Intelligence",
    "Climate Change",
    "Future of Space Exploration",
    "Quantum Computing",
    "AI in Healthcare",
]

# ---------------------------------------------------------------------------
# CSS — modern AI SaaS palette
# ---------------------------------------------------------------------------
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { box-sizing: border-box; }

:root {
    --bg:      #f5f7fb;
    --surface: #ffffff;
    --border:  #e4e8f0;
    --accent:  #5b6cff;
    --accent2: #7c89ff;
    --text:    #1d2433;
    --muted:   #7b8496;
    --subtle:  #eef2ff;
    --radius:  14px;
}

body, .gradio-container, .gradio-container * {
    font-family: 'Inter', -apple-system, sans-serif !important;
}

.gradio-container {
    max-width: 1100px !important;
    margin: 0 auto !important;
    background: var(--bg) !important;
}

h1, h2, h3, p, label, span {
    color: var(--text) !important;
    font-weight: 400 !important;
    margin: 0 !important;
}

textarea, input[type=text] {
    background: var(--surface) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 12px !important;
    color: var(--text) !important;
    font-size: 0.95rem !important;
    padding: 12px 16px !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
textarea:focus, input[type=text]:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(91,108,255,0.12) !important;
    outline: none !important;
}
textarea::placeholder, input::placeholder { color: #b0b8c8 !important; }

#send-btn {
    background: var(--accent) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    width: 42px !important;
    min-width: 42px !important;
    height: 42px !important;
    font-size: 1.1rem !important;
    padding: 0 !important;
    cursor: pointer !important;
    box-shadow: 0 2px 10px rgba(91,108,255,0.35) !important;
    transition: all 0.15s !important;
    flex-shrink: 0 !important;
}
#send-btn:hover {
    background: var(--accent2) !important;
    transform: scale(1.06) !important;
    box-shadow: 0 4px 14px rgba(91,108,255,0.4) !important;
}

#clr-btn {
    background: transparent !important;
    color: var(--muted) !important;
    border: none !important;
    font-size: 0.82rem !important;
    padding: 6px 10px !important;
    min-width: unset !important;
    box-shadow: none !important;
}
#clr-btn:hover { color: var(--text) !important; }

.chip-btn {
    background: var(--surface) !important;
    color: var(--muted) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 999px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding: 5px 14px !important;
    cursor: pointer !important;
    transition: all 0.15s !important;
    box-shadow: none !important;
    min-width: unset !important;
    height: auto !important;
    min-height: unset !important;
}
.chip-btn:hover {
    background: var(--subtle) !important;
    color: var(--accent) !important;
    border-color: var(--accent) !important;
}

.tab-nav { border-bottom: 1px solid var(--border) !important; margin-bottom: 20px !important; }
.tab-nav button {
    background: transparent !important;
    border: none !important;
    color: var(--muted) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    padding: 10px 18px !important;
    box-shadow: none !important;
}
.tab-nav button.selected {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    font-weight: 600 !important;
}

.report-out { font-size: 0.94rem !important; line-height: 1.85 !important; }
.report-out h1 {
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    margin-bottom: 16px !important;
    padding-bottom: 12px !important;
    border-bottom: 1px solid var(--border) !important;
}
.report-out h2 {
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    color: var(--accent) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.9px !important;
    margin-top: 28px !important;
    margin-bottom: 10px !important;
}
.report-out ul { padding-left: 18px !important; }
.report-out ul li { margin-bottom: 5px !important; }
.report-out p { margin-bottom: 12px !important; }
.report-out hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 24px 0 !important; }
.report-out em { color: var(--muted) !important; font-size: 0.82rem !important; }
.report-out a { color: var(--accent) !important; word-break: break-all !important; text-decoration: none !important; }
.report-out a:hover { text-decoration: underline !important; }

.sources-out { font-size: 0.9rem !important; line-height: 1.75 !important; }
.sources-out h3 { font-size: 0.92rem !important; font-weight: 600 !important; margin: 0 0 4px !important; }
.sources-out a { color: var(--accent) !important; word-break: break-all !important; text-decoration: none !important; font-size: 0.83rem !important; }
.sources-out a:hover { text-decoration: underline !important; }
.sources-out hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 16px 0 !important; }

.history-panel { font-size: 0.85rem !important; line-height: 1.5 !important; }
.history-panel strong { font-size: 0.84rem !important; font-weight: 500 !important; display: block !important; margin-bottom: 1px !important; }
.history-panel em { font-size: 0.72rem !important; color: var(--muted) !important; font-style: normal !important; }
.history-panel hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 8px 0 !important; }

#txt-btn, #pdf-btn {
    min-height: 48px !important;
    border-radius: 12px !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    transition: all 0.18s !important;
    border: none !important;
}
#txt-btn {
    background: var(--surface) !important;
    color: var(--text) !important;
    border: 1.5px solid var(--border) !important;
}
#txt-btn:hover:not(:disabled) {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    background: var(--subtle) !important;
}
#pdf-btn {
    background: var(--accent) !important;
    color: #fff !important;
    box-shadow: 0 2px 10px rgba(91,108,255,0.3) !important;
}
#pdf-btn:hover:not(:disabled) {
    background: var(--accent2) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(91,108,255,0.4) !important;
}
#txt-btn:disabled, #pdf-btn:disabled {
    opacity: 0.35 !important;
    cursor: not-allowed !important;
}

.history-radio { gap: 0 !important; }
.history-radio .wrap { gap: 0 !important; flex-direction: column !important; }
.history-radio label {
    display: block !important;
    padding: 8px 10px !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    font-size: 0.82rem !important;
    color: var(--text) !important;
    line-height: 1.4 !important;
    border: none !important;
    background: transparent !important;
    transition: background 0.12s !important;
    margin-bottom: 2px !important;
}
.history-radio label:hover { background: var(--subtle) !important; }
.history-radio label.selected,
.history-radio input:checked + span { color: var(--accent) !important; font-weight: 600 !important; }
.history-radio input[type=radio] { display: none !important; }
.history-radio .wrap > label > span:first-child { display: none !important; }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
"""

# ---------------------------------------------------------------------------
# Empty state strings
# ---------------------------------------------------------------------------
EMPTY_REPORT_MD = (
    "**Start by entering a research topic above.**\n\n"
    "Your AI-generated report will appear here — structured with an executive summary, "
    "key findings, background, current developments, applications, challenges, and future outlook."
)

EMPTY_SOURCES_MD = (
    "**No sources yet.**\n\n"
    "After you generate a report, all web sources used to ground the AI response "
    "will be listed here with titles, URLs, and summaries."
)

# ---------------------------------------------------------------------------
# Helpers: history list and report loader
# ---------------------------------------------------------------------------

def _get_history_choices() -> list:
    """Return list of (label, filename) tuples for the sidebar radio."""
    if _agent is None:
        return []
    reports = _agent.list_saved_reports()
    choices = []
    for r in reports:
        topic = r["topic"][:38] + ("…" if len(r["topic"]) > 38 else "")
        date  = r["saved_at"][5:16].replace("T", " ") if r.get("saved_at") else "—"
        label = f"{topic}  ·  {date}"
        choices.append((label, r["filename"]))
    return choices


def _build_history_md() -> str:
    """Fallback markdown (used for refresh button)."""
    choices = _get_history_choices()
    if not choices:
        return "*No research history yet.\nGenerate your first report above.*"
    return ""


def load_saved_report(filename: str) -> tuple:
    """Load a previously saved report from disk and populate all tabs.
    Returns None (no-op) when filename is empty to avoid overwriting
    a freshly generated report when the radio resets to value=None.
    """
    if not filename:
        # Do not update anything — prevents wiping a just-generated report
        return (
            gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
        )
    from mcp_services import _do_read_report
    data = _do_read_report(filename)
    if not data:
        raise gr.Error(f"Could not load report: {filename}")

    summary  = data.get("summary", "")
    sources  = data.get("sources", [])
    metadata = data.get("metadata", {})
    topic    = data.get("topic", "")

    # Rebuild sources markdown
    sources_lines = []
    for i, s in enumerate(sources, 1):
        t = s.get("title", "").strip()
        u = s.get("url", "").strip()
        sn = s.get("snippet", "").strip()
        sources_lines.append(f"### Source {i}: {t}\n\n🔗 [{u}]({u})\n\n{sn}\n\n---")
    sources_md = "\n\n".join(sources_lines) or "*No sources recorded.*"

    # Find saved file paths
    from pathlib import Path as _Path
    stem     = filename.replace(".json", "")
    txt_path = str((_Path("reports") / f"{stem}.txt").resolve())
    pdf_path = str((_Path("reports") / f"{stem}.pdf").resolve())
    txt_ok   = _Path(txt_path).exists()
    pdf_ok   = _Path(pdf_path).exists()

    saved_info = (
        f"✅  Loaded from saved report\n\n"
        f"JSON : reports/{filename}\n"
        f"TXT  : {txt_path if txt_ok else '—'}\n"
        f"PDF  : {pdf_path if pdf_ok else '—'}"
    )

    session = {"topic": topic, "summary": summary, "paths": {
        "txt": txt_path if txt_ok else None,
        "pdf": pdf_path if pdf_ok else None,
    }}

    return (
        summary,
        sources_md,
        saved_info,
        f"{metadata.get('elapsed_sec', '—')}s",
        f"{metadata.get('tokens_used', 0):,} tokens",
        f"{'Live' if metadata.get('search_live') else 'Demo'}",
        gr.update(value=txt_path if txt_ok else None,
                  label="📄  Download TXT" if txt_ok else "📄  Not available",
                  interactive=txt_ok),
        gr.update(value=pdf_path if pdf_ok else None,
                  label="📕  Download PDF" if pdf_ok else "📕  Not available",
                  interactive=pdf_ok),
        session,
    )


# ---------------------------------------------------------------------------
# Pipeline function
# ---------------------------------------------------------------------------

def run_pipeline(topic: str, session: dict) -> tuple:
    """
    Runs the full research pipeline and returns updated UI component values.
    Uses gr.State for per-session data — no global mutable state.
    """
    if _agent is None:
        raise gr.Error(_agent_error or "Agent failed to initialise.")
    if not topic or not topic.strip():
        raise gr.Error("Please enter a research topic first.")

    result: ResearchResult = _agent.run(topic, progress_cb=None)

    if not result.ok:
        raise gr.Error(result.error)

    # Build sources markdown
    sources_lines = []
    for i, s in enumerate(result.sources, 1):
        title   = s.get("title",   "").strip()
        url     = s.get("url",     "").strip()
        snippet = s.get("snippet", "").strip()
        sources_lines.append(
            f"### Source {i}: {title}\n\n"
            f"🔗 [{url}]({url})\n\n"
            f"{snippet}\n\n---"
        )
    sources_md = "\n\n".join(sources_lines)

    # Saved files info
    sp = result.saved_paths
    saved_info = (
        "✅  Auto-saved by Filesystem MCP\n\n"
        f"JSON : {sp.get('json', '—')}\n"
        f"TXT  : {sp.get('txt',  '—')}\n"
        f"PDF  : {sp.get('pdf') or '(install reportlab for PDF support)'}"
    )

    m        = result.metadata
    txt_path = sp.get("txt") or None
    pdf_path = sp.get("pdf") or None
    txt_ok   = bool(txt_path and Path(txt_path).exists())
    pdf_ok   = bool(pdf_path and Path(pdf_path).exists())

    new_session = {
        "topic":   result.topic,
        "summary": result.summary,
        "paths":   sp,
    }

    return (
        result.summary,
        sources_md,
        saved_info,
        f"{m['elapsed_sec']}s",
        f"{m['tokens_used']:,} tokens",
        f"{'Live' if m['search_live'] else 'Demo'}",
        gr.update(choices=_get_history_choices(), value=None),
        gr.update(value=txt_path if txt_ok else None,
                  label="📄  Download TXT" if txt_ok else "📄  Generate a report first",
                  interactive=txt_ok),
        gr.update(value=pdf_path if pdf_ok else None,
                  label="📕  Download PDF" if pdf_ok else "📕  Generate a report first",
                  interactive=pdf_ok),
        new_session,
    )


def clear_all(session: dict) -> tuple:
    """Reset all UI components and session state."""
    return (
        "",
        EMPTY_REPORT_MD,
        EMPTY_SOURCES_MD,
        "No report saved yet.\nGenerate a report and it will be auto-saved here.",
        "", "", "",
        gr.update(choices=_get_history_choices(), value=None),
        gr.update(value=None, interactive=False, label="📄  Generate a report first"),
        gr.update(value=None, interactive=False, label="📕  Generate a report first"),
        {},
    )


def fill_topic(chip_label: str) -> str:
    """Autofill topic input from a suggestion chip."""
    return chip_label


# ---------------------------------------------------------------------------
# Build UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="AI Research Assistant", css=CSS) as demo:

    session_state = gr.State({})

    # ── Hero ──────────────────────────────────────────────────────────────
    gr.HTML("""
    <div style="padding: 28px 0 6px;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:6px;">
            <div style="width:32px; height:32px; background:#5b6cff; border-radius:8px;
                        display:flex; align-items:center; justify-content:center; flex-shrink:0;">
                <span style="color:#fff; font-size:1rem; line-height:1;">✦</span>
            </div>
            <h1 style="font-size:1.45rem !important; font-weight:700 !important;
                       color:#1d2433 !important; margin:0 !important; line-height:1.2;">
                AI Research Assistant
            </h1>
        </div>
        <p style="color:#7b8496 !important; font-size:0.88rem; margin:0 0 12px 42px !important; line-height:1.5;">
            AI-powered research with live web intelligence and exportable reports.
        </p>
        <div style="display:flex; flex-wrap:wrap; gap:18px; margin-left:42px; margin-bottom:4px;">
            <span style="font-size:0.79rem; color:#7b8496; display:flex; align-items:center; gap:5px;">
                <span style="color:#5b6cff; font-size:0.6rem;">●</span> Live web research
            </span>
            <span style="font-size:0.79rem; color:#7b8496; display:flex; align-items:center; gap:5px;">
                <span style="color:#5b6cff; font-size:0.6rem;">●</span> AI-generated summaries
            </span>
            <span style="font-size:0.79rem; color:#7b8496; display:flex; align-items:center; gap:5px;">
                <span style="color:#5b6cff; font-size:0.6rem;">●</span> Source-backed insights
            </span>
            <span style="font-size:0.79rem; color:#7b8496; display:flex; align-items:center; gap:5px;">
                <span style="color:#5b6cff; font-size:0.6rem;">●</span> Export to TXT / PDF
            </span>
        </div>
    </div>
    """)

    # ── Input row ─────────────────────────────────────────────────────────
    with gr.Row():
        with gr.Column(scale=10):
            topic_box = gr.Textbox(
                placeholder="e.g. Quantum Computing, Climate Change, AI in Healthcare…",
                show_label=False, lines=1, max_lines=1, container=False,
            )
        with gr.Column(scale=1, min_width=56):
            gen_btn = gr.Button("↑", elem_id="send-btn")
        with gr.Column(scale=1, min_width=60):
            clr_btn = gr.Button("Clear", elem_id="clr-btn")

    # ── Suggestion chips ───────────────────────────────────────────────────
    with gr.Row():
        chip_btns = [
            gr.Button(label, elem_classes=["chip-btn"], size="sm")
            for label in TOPIC_SUGGESTIONS
        ]

    # Hidden stat outputs
    stat_time   = gr.Textbox(visible=False)
    stat_tokens = gr.Textbox(visible=False)
    stat_search = gr.Textbox(visible=False)

    # ── Main layout ────────────────────────────────────────────────────────
    with gr.Row():

        # Sidebar
        with gr.Column(scale=1, min_width=220):
            gr.HTML("""
            <div style="padding: 4px 2px 10px;">
                <p style="font-size:0.68rem !important; font-weight:700 !important;
                          color:#7b8496 !important; text-transform:uppercase;
                          letter-spacing:1px; margin:0 !important;">
                    Recent Research Reports
                </p>
            </div>
            """)
            history_radio = gr.Radio(
                choices=_get_history_choices(),
                value=None,
                show_label=False,
                elem_classes=["history-radio"],
                container=False,
            )
            refresh_btn = gr.Button("↺  Refresh", size="sm")

        # Main panel
        with gr.Column(scale=4):
            with gr.Tabs():
                with gr.TabItem("📋  Report"):
                    output_md = gr.Markdown(
                        EMPTY_REPORT_MD,
                        elem_classes=["report-out"],
                    )
                with gr.TabItem("🔗  Sources"):
                    sources_md_out = gr.Markdown(
                        EMPTY_SOURCES_MD,
                        elem_classes=["sources-out"],
                    )
                with gr.TabItem("💾  Saved Files"):
                    saved_box = gr.Textbox(
                        show_label=False, interactive=False,
                        lines=4,
                        value="No report saved yet.\nGenerate a report and it will be auto-saved here.",
                    )

    # ── Export section ─────────────────────────────────────────────────────
    gr.HTML("""
    <div style="text-align:center; padding: 22px 0 10px;">
        <p style="color:#7b8496 !important; font-size:0.82rem; margin:0 0 12px !important;
                  font-weight:500; letter-spacing:0.3px;">
            Export your report
        </p>
    </div>
    """)
    with gr.Row(equal_height=True):
        txt_btn = gr.DownloadButton(
            label="📄  Generate a report first",
            value=None, visible=True, interactive=False,
            scale=1, elem_id="txt-btn",
        )
        pdf_btn = gr.DownloadButton(
            label="📕  Generate a report first",
            value=None, visible=True, interactive=False,
            scale=1, elem_id="pdf-btn",
        )

    # ── Footer ─────────────────────────────────────────────────────────────
    gr.HTML("""
    <div style="text-align:center; padding: 24px 0 8px;
                border-top: 1px solid #e4e8f0; margin-top: 12px;">
        <p style="color:#b0b8c8 !important; font-size:0.76rem;
                  margin:0 !important; letter-spacing:0.2px;">
            Built with&nbsp;
            <span style="color:#7b8496; font-weight:500;">Gradio</span>
            &nbsp;•&nbsp;
            <span style="color:#7b8496; font-weight:500;">Groq API</span>
            &nbsp;•&nbsp;
            <span style="color:#7b8496; font-weight:500;">MCP-inspired architecture</span>
        </p>
    </div>
    """)

    # ── Wire up events ─────────────────────────────────────────────────────
    pipeline_outputs = [
        output_md, sources_md_out, saved_box,
        stat_time, stat_tokens, stat_search,
        history_radio, txt_btn, pdf_btn, session_state,
    ]
    clear_outputs = [
        topic_box, output_md, sources_md_out, saved_box,
        stat_time, stat_tokens, stat_search,
        history_radio, txt_btn, pdf_btn, session_state,
    ]

    gen_btn.click(fn=run_pipeline, inputs=[topic_box, session_state], outputs=pipeline_outputs)
    topic_box.submit(fn=run_pipeline, inputs=[topic_box, session_state], outputs=pipeline_outputs)
    clr_btn.click(fn=clear_all, inputs=[session_state], outputs=clear_outputs)
    refresh_btn.click(fn=lambda: gr.update(choices=_get_history_choices(), value=None), inputs=[], outputs=[history_radio])

    # Sidebar radio — load saved report on click
    history_radio.change(fn=load_saved_report, inputs=[history_radio], outputs=[
        output_md, sources_md_out, saved_box,
        stat_time, stat_tokens, stat_search,
        txt_btn, pdf_btn, session_state,
    ])

    # Chip buttons — autofill topic input on click
    for chip in chip_btns:
        chip.click(fn=fill_topic, inputs=[chip], outputs=[topic_box])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import threading
    import webbrowser

    def _open_browser():
        time.sleep(2)
        webbrowser.open("http://localhost:7860")

    threading.Thread(target=_open_browser, daemon=True).start()

    demo.launch(
        server_name="localhost",
        server_port=7860,
        share=False,
        allowed_paths=["reports"],
    )
