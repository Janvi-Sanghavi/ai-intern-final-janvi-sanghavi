"""
ui.py
-----
Gradio frontend for the AI Research Assistant.

Key improvements over v1:
  • No global mutable state — uses gr.State for per-session data
  • Download buttons show a tooltip when disabled so users know why
  • All UI logic separated from agent / MCP code
  • Progress feedback at every pipeline stage
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
# CSS
# ---------------------------------------------------------------------------
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { box-sizing: border-box; }

:root {
    --bg:      #f9f9f8;
    --surface: #ffffff;
    --border:  #e8e8e5;
    --accent:  #c96442;
    --accent2: #d97757;
    --text:    #1a1a19;
    --muted:   #8f8f8a;
    --subtle:  #f2f2f0;
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
    box-shadow: 0 0 0 3px rgba(201,100,66,0.1) !important;
    outline: none !important;
}
textarea::placeholder, input::placeholder { color: #bbbbb7 !important; }

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
    box-shadow: 0 2px 8px rgba(201,100,66,0.3) !important;
    transition: all 0.15s !important;
    flex-shrink: 0 !important;
}
#send-btn:hover {
    background: var(--accent2) !important;
    transform: scale(1.05) !important;
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
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: var(--accent) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
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
.history-panel hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 6px 0 !important; }

#txt-btn, #pdf-btn {
    min-height: 48px !important;
    border-radius: 12px !important;
    font-size: 0.92rem !important;
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
}
#pdf-btn {
    background: var(--accent) !important;
    color: #fff !important;
    box-shadow: 0 2px 10px rgba(201,100,66,0.3) !important;
}
#pdf-btn:hover:not(:disabled) {
    background: var(--accent2) !important;
    transform: translateY(-1px) !important;
}
#txt-btn:disabled, #pdf-btn:disabled {
    opacity: 0.38 !important;
    cursor: not-allowed !important;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
"""

# ---------------------------------------------------------------------------
# Helper: build history markdown
# ---------------------------------------------------------------------------

def _build_history_md() -> str:
    if _agent is None:
        return "*Agent not initialised — check GROQ_API_KEY.*"
    reports = _agent.list_saved_reports()
    if not reports:
        return "*No research history yet.*"
    lines = []
    for r in reports:
        topic = r["topic"][:42] + ("..." if len(r["topic"]) > 42 else "")
        date  = r["saved_at"][5:16].replace("T", " ") if r.get("saved_at") else "—"
        lines.append(f"**{topic}**\n\n*{date}*")
    return "\n\n---\n\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline function — returns outputs + updated session state
# ---------------------------------------------------------------------------

def run_pipeline(topic: str, session: dict, progress=gr.Progress()) -> tuple:
    """
    Runs the full research pipeline and returns updated UI component values.
    Uses `session` (gr.State) instead of a global variable.
    """
    if _agent is None:
        raise gr.Error(_agent_error or "Agent failed to initialise.")
    if not topic or not topic.strip():
        raise gr.Error("Please enter a research topic first.")

    result: ResearchResult = _agent.run(topic, progress_cb=progress)

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
        "Auto-saved by Filesystem MCP\n\n"
        f"JSON: {sp.get('json', '—')}\n"
        f"TXT:  {sp.get('txt',  '—')}\n"
        f"PDF:  {sp.get('pdf') or '(install reportlab for PDF support)'}"
    )

    m        = result.metadata
    txt_path = sp.get("txt") or None
    pdf_path = sp.get("pdf") or None
    txt_ok   = bool(txt_path and Path(txt_path).exists())
    pdf_ok   = bool(pdf_path and Path(pdf_path).exists())

    # Store result in session state (no global mutation)
    new_session = {
        "topic":   result.topic,
        "summary": result.summary,
        "paths":   sp,
    }

    return (
        result.summary,                                     # report tab
        sources_md,                                         # sources tab
        saved_info,                                         # saved files tab
        f"{m['elapsed_sec']}s",                            # stat: time
        f"{m['tokens_used']:,} tokens",                    # stat: tokens
        f"{'Live' if m['search_live'] else 'Demo'}",       # stat: search mode
        _build_history_md(),                               # history panel
        gr.update(value=txt_path if txt_ok else None,      # txt download btn
                  label="📄  Download TXT" if txt_ok else "📄  Generate a report first",
                  interactive=txt_ok),
        gr.update(value=pdf_path if pdf_ok else None,      # pdf download btn
                  label="📕  Download PDF" if pdf_ok else "📕  Generate a report first",
                  interactive=pdf_ok),
        new_session,                                        # session state
    )


def clear_all(session: dict) -> tuple:
    """Reset all UI components and session state."""
    return (
        "",                                                              # topic
        "*Your report will appear here…*",                              # report
        "*Sources will appear after generation.*",                       # sources
        "No report generated yet.",                                     # saved
        "", "", "",                                                      # stats
        _build_history_md(),                                            # history
        gr.update(value=None, interactive=False,
                  label="📄  Generate a report first"),                 # txt btn
        gr.update(value=None, interactive=False,
                  label="📕  Generate a report first"),                 # pdf btn
        {},                                                             # session
    )


# ---------------------------------------------------------------------------
# Build UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="AI Research Assistant", css=CSS) as demo:

    # Per-session state — replaces global _current dict
    session_state = gr.State({})

    gr.HTML("""
    <div style="padding: 24px 0 8px; text-align: left;">
        <h1 style="font-size: 1.4rem; font-weight: 600; margin-bottom: 4px !important;">
            AI Research Assistant
        </h1>
        <p style="color: #8f8f8a; font-size: 0.88rem;">
            Ask anything. Get a structured, source-backed research report in seconds.
        </p>
    </div>
    """)

    # Input row
    with gr.Row():
        with gr.Column(scale=10):
            topic_box = gr.Textbox(
                placeholder="What do you want to research?",
                show_label=False, lines=1, max_lines=1, container=False,
            )
        with gr.Column(scale=1, min_width=56):
            gen_btn = gr.Button("↑", elem_id="send-btn")
        with gr.Column(scale=1, min_width=60):
            clr_btn = gr.Button("Clear", elem_id="clr-btn")

    # Hidden stat outputs
    stat_time   = gr.Textbox(visible=False)
    stat_tokens = gr.Textbox(visible=False)
    stat_search = gr.Textbox(visible=False)

    with gr.Row():
        # Sidebar — history
        with gr.Column(scale=1, min_width=220):
            gr.HTML("""
            <div style='padding: 4px 2px 12px'>
                <p style='font-size:0.7rem; font-weight:600; color:#8f8f8a;
                          text-transform:uppercase; letter-spacing:0.8px; margin:0'>
                    Recents
                </p>
            </div>
            """)
            archive_md  = gr.Markdown(_build_history_md(), elem_classes=["history-panel"])
            refresh_btn = gr.Button("↺  Refresh", size="sm")

        # Main panel — tabs
        with gr.Column(scale=4):
            with gr.Tabs():
                with gr.TabItem("Report"):
                    output_md = gr.Markdown(
                        "*Your report will appear here…*",
                        elem_classes=["report-out"],
                    )
                with gr.TabItem("Sources"):
                    sources_md_out = gr.Markdown(
                        "*Sources will appear after generation.*",
                        elem_classes=["sources-out"],
                    )
                with gr.TabItem("Saved Files"):
                    saved_box = gr.Textbox(
                        show_label=False, interactive=False,
                        lines=4, value="No report generated yet.",
                    )

    # Export section
    gr.HTML("""
    <div style='text-align:center; padding: 20px 0 8px'>
        <p style='color:#8f8f8a; font-size:0.85rem; margin:0 0 12px; font-weight:500'>
            Export report
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

    # Wire up events
    pipeline_outputs = [
        output_md, sources_md_out, saved_box,
        stat_time, stat_tokens, stat_search,
        archive_md, txt_btn, pdf_btn, session_state,
    ]
    clear_outputs = [
        topic_box, output_md, sources_md_out, saved_box,
        stat_time, stat_tokens, stat_search,
        archive_md, txt_btn, pdf_btn, session_state,
    ]

    gen_btn.click(fn=run_pipeline, inputs=[topic_box, session_state], outputs=pipeline_outputs)
    topic_box.submit(fn=run_pipeline, inputs=[topic_box, session_state], outputs=pipeline_outputs)
    clr_btn.click(fn=clear_all, inputs=[session_state], outputs=clear_outputs)
    refresh_btn.click(fn=_build_history_md, inputs=[], outputs=[archive_md])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import threading
    import time
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
