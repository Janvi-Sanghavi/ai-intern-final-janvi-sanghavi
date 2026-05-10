"""
agent.py
--------
ResearchAgent orchestrates the full pipeline:

  Stage 1 → MCP #1 (WebSearchMCPServer)  — fetch web context
  Stage 2 → Groq API (LLaMA-3.3-70B)    — generate structured report
  Stage 3 → MCP #2 (FilesystemMCPServer) — auto-save JSON / TXT / PDF

Uses in-process MCP helpers so the Gradio UI doesn't need to spawn subprocesses,
while the full MCP servers (mcp_services.py) remain runnable over stdio for any
external MCP client.
"""

from __future__ import annotations

import logging
import os
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime

from dotenv import load_dotenv
from groq import Groq

from mcp_services import (
    format_search_results_for_prompt,
    list_reports_inprocess,
    save_report_inprocess,
    search_web_inprocess,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
_groq_client: Groq | None = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

MODEL      = "llama-3.3-70b-versatile"
MAX_TOKENS = 4096

# ---------------------------------------------------------------------------
# Structured result — replaces the raw dict / global mutable state
# ---------------------------------------------------------------------------

@dataclass
class ResearchResult:
    """Immutable, typed result returned by ResearchAgent.run()."""
    topic:       str
    summary:     str
    sources:     list
    metadata:    dict
    saved_paths: dict
    error:       str = ""

    @property
    def ok(self) -> bool:
        return not self.error


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert AI Research Assistant. Generate structured, insightful,
    and well-cited research summaries. Always respond in this exact Markdown format:

    # Research Summary: {TOPIC}

    ## 📋 Executive Summary
    2-3 sentence high-level overview.

    ## 🔍 Key Findings
    - Finding 1
    - Finding 2
    - Finding 3
    - Finding 4
    - Finding 5

    ## 📚 Background & Context
    2-3 paragraphs of historical and foundational context.

    ## 🚀 Current Developments
    2-3 paragraphs on latest trends, news, and advancements.

    ## 💡 Applications & Use Cases
    2-3 paragraphs on real-world applications.

    ## ⚠️ Challenges & Limitations
    - Challenge 1
    - Challenge 2
    - Challenge 3

    ## 🔮 Future Outlook
    1-2 paragraphs on where this field is heading.

    ## 🔗 Sources Referenced
    List each URL on its own line as a markdown bullet:
    - https://example.com/article-one
    - https://example.com/article-two

    ---
    *Generated on {DATE} by AI Research Assistant*
""").strip()


# ---------------------------------------------------------------------------
# ResearchAgent
# ---------------------------------------------------------------------------

class ResearchAgent:
    """
    Orchestrates:
      WebSearchMCPServer  →  Groq LLaMA-3.3-70B  →  FilesystemMCPServer

    Each MCP server is called in-process via its helper function so no
    subprocess management is needed inside the Gradio UI.  The same MCP
    servers can also be run standalone (stdio transport) for external clients.
    """

    def __init__(self) -> None:
        if not GROQ_API_KEY:
            raise EnvironmentError(
                "GROQ_API_KEY is missing. Add it to your .env file and restart."
            )
        logger.info("[ResearchAgent] Initialized — model=%s", MODEL)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, topic: str, *, progress_cb=None) -> ResearchResult:
        """
        Run the full research pipeline.

        Args:
            topic:       The research topic entered by the user.
            progress_cb: Optional callable(fraction, desc) for UI progress bars.

        Returns:
            A ResearchResult dataclass (check .ok / .error before using).
        """
        topic = topic.strip()
        if not topic:
            return ResearchResult(
                topic="", summary="", sources=[], metadata={}, saved_paths={},
                error="Topic cannot be empty.",
            )

        start = time.time()
        self._progress(progress_cb, 0.05, "Starting pipeline…")

        # Stage 1 — MCP #1: Web Search
        self._progress(progress_cb, 0.15, "🌐 MCP #1 · Web Search — querying SerpAPI…")
        search_result  = search_web_inprocess(topic, num_results=5)
        search_context = format_search_results_for_prompt(search_result)

        # Stage 2 — Groq API
        self._progress(progress_cb, 0.45, "⚡ Groq API — generating report with LLaMA-3.3-70B…")
        try:
            summary, tokens_used = self._call_groq(topic, search_context)
        except Exception as exc:
            logger.error("[ResearchAgent] Groq API error: %s", exc)
            return ResearchResult(
                topic=topic, summary="", sources=[], metadata={}, saved_paths={},
                error=f"Groq API error: {exc}",
            )

        elapsed  = round(time.time() - start, 2)
        metadata = {
            "model":        MODEL,
            "tokens_used":  tokens_used,
            "elapsed_sec":  elapsed,
            "generated_at": datetime.now().isoformat(),
            "search_live":  search_result["is_live"],
        }

        # Stage 3 — MCP #2: Filesystem
        self._progress(progress_cb, 0.85, "💾 MCP #2 · Filesystem — saving report…")
        saved_paths = save_report_inprocess(
            topic=topic,
            summary=summary,
            sources=search_result["results"],
            metadata=metadata,
        )

        self._progress(progress_cb, 1.0, "✅ Done!")
        logger.info("[ResearchAgent] Completed in %.2fs | %d tokens | '%s'",
                    elapsed, tokens_used, topic)

        return ResearchResult(
            topic=topic,
            summary=summary,
            sources=search_result["results"],
            metadata=metadata,
            saved_paths=saved_paths,
        )

    def list_saved_reports(self) -> list:
        """Return metadata for recent saved reports via FilesystemMCP."""
        return list_reports_inprocess(limit=10)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_groq(self, topic: str, search_context: str) -> tuple[str, int]:
        """Send the prompt to Groq and return (summary_text, total_tokens)."""
        system = (
            SYSTEM_PROMPT
            .replace("{TOPIC}", topic)
            .replace("{DATE}", datetime.now().strftime("%B %d, %Y"))
        )
        user_msg = (
            f"Generate a comprehensive research summary on: **{topic}**\n\n"
            f"Use these web search results as your primary sources:\n\n"
            f"{search_context}\n\n"
            f"Supplement with your knowledge where helpful."
        )

        assert _groq_client is not None, "Groq client not initialised"
        resp = _groq_client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0.6,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_msg},
            ],
        )
        return resp.choices[0].message.content, resp.usage.total_tokens

    @staticmethod
    def _progress(cb, fraction: float, desc: str) -> None:
        if cb is not None:
            try:
                cb(fraction, desc=desc)
            except Exception:
                pass
