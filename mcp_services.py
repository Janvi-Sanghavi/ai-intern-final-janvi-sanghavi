"""
mcp_services.py
---------------
Two genuine MCP servers built with the official `mcp` Python SDK:

  • WebSearchMCPServer  — wraps SerpAPI (Google Search) as an MCP tool
  • FilesystemMCPServer — exposes save / list / read as MCP tools

Each server is also runnable standalone (stdio transport) so any MCP-compatible
client (Claude Desktop, MCP Inspector, etc.) can connect to it directly.

For in-process use by the Gradio UI, call the helper coroutines at the bottom
of this file instead of spinning up the full servers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional PDF support
# ---------------------------------------------------------------------------
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


# ===========================================================================
# MCP SERVER #1 — Web Search
# ===========================================================================

WEB_SEARCH_SERVER_NAME = "web-search-mcp"
WEB_SEARCH_VERSION     = "2.0.0"

web_search_server = Server(WEB_SEARCH_SERVER_NAME)


@web_search_server.list_tools()
async def list_web_search_tools() -> list[Tool]:
    """Advertise the search tool to any MCP client."""
    return [
        Tool(
            name="search_web",
            description=(
                "Search the web using Google (via SerpAPI) and return the top results. "
                "Falls back to curated stub results when no API key is configured."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query":       {"type": "string",  "description": "Search query"},
                    "num_results": {"type": "integer", "description": "Number of results (1-10)", "default": 5},
                },
                "required": ["query"],
            },
        )
    ]


@web_search_server.call_tool()
async def call_web_search_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle a tool call from an MCP client."""
    if name != "search_web":
        raise ValueError(f"Unknown tool: {name}")

    query       = arguments["query"]
    num_results = int(arguments.get("num_results", 5))
    result      = _do_web_search(query, num_results)

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def run_web_search_server() -> None:
    """Run the web-search MCP server over stdio (for standalone use)."""
    async with stdio_server() as (read_stream, write_stream):
        await web_search_server.run(read_stream, write_stream,
                                    web_search_server.create_initialization_options())


# ---------------------------------------------------------------------------
# In-process helper — call this from agent.py without spawning a subprocess
# ---------------------------------------------------------------------------

def search_web_inprocess(query: str, num_results: int = 5) -> dict:
    """
    Call the web-search MCP tool in-process.
    Returns the same JSON structure the MCP tool would return to a remote client.
    """
    logger.info("[%s v%s] search_web_inprocess: '%s'", WEB_SEARCH_SERVER_NAME, WEB_SEARCH_VERSION, query)
    return _do_web_search(query, num_results)


def format_search_results_for_prompt(search_result: dict) -> str:
    """Format MCP search results into a string suitable for LLM context injection."""
    blocks = []
    for i, r in enumerate(search_result.get("results", []), 1):
        blocks.append(
            f"Source {i}: {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Summary: {r['snippet']}"
        )
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Internal implementation shared by the MCP handler and in-process helper
# ---------------------------------------------------------------------------

def _do_web_search(query: str, num_results: int) -> dict:
    api_key = os.environ.get("SERP_API_KEY", "")
    is_live = bool(api_key)

    if not is_live:
        logger.warning("[%s] No SERP_API_KEY — using stub results.", WEB_SEARCH_SERVER_NAME)
        return _build_search_response(query, _stub_results(query), is_live=False)

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": api_key, "engine": "google",
                    "num": num_results, "hl": "en", "gl": "us"},
            timeout=15,
        )
        resp.raise_for_status()
        organic = resp.json().get("organic_results", [])
        results = [
            {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
            for r in organic[:num_results]
        ]
        logger.info("[%s] Live search — %d results.", WEB_SEARCH_SERVER_NAME, len(results))
        return _build_search_response(query, results, is_live=True)

    except requests.RequestException as exc:
        logger.error("[%s] SerpAPI error: %s — falling back to stubs.", WEB_SEARCH_SERVER_NAME, exc)
        return _build_search_response(query, _stub_results(query), is_live=False)


def _build_search_response(query: str, results: list, *, is_live: bool) -> dict:
    return {
        "service": WEB_SEARCH_SERVER_NAME,
        "version": WEB_SEARCH_VERSION,
        "query":   query,
        "is_live": is_live,
        "results": results,
    }


def _stub_results(query: str) -> list:
    return [
        {"title": f"Overview of {query}",
         "url": f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
         "snippet": f"Comprehensive overview of {query} covering history, key concepts, and significance."},
        {"title": f"Latest Research on {query}",
         "url": "https://scholar.google.com",
         "snippet": f"Peer-reviewed studies and academic papers on {query} from leading researchers worldwide."},
        {"title": f"{query} — Trends & Analysis 2026",
         "url": "https://www.researchgate.net",
         "snippet": f"Current trends, market analysis, and future projections for {query}."},
        {"title": f"Real-World Applications of {query}",
         "url": "https://www.nature.com",
         "snippet": f"Case studies demonstrating the practical impact of {query}."},
        {"title": f"Challenges in {query}",
         "url": "https://www.sciencedirect.com",
         "snippet": f"Key challenges, limitations, and open problems in the domain of {query}."},
    ]


# ===========================================================================
# MCP SERVER #2 — Filesystem
# ===========================================================================

FILESYSTEM_SERVER_NAME = "filesystem-mcp"
FILESYSTEM_VERSION     = "2.0.0"

filesystem_server = Server(FILESYSTEM_SERVER_NAME)


@filesystem_server.list_tools()
async def list_filesystem_tools() -> list[Tool]:
    """Advertise filesystem tools to any MCP client."""
    return [
        Tool(
            name="save_report",
            description="Save a research report to disk in JSON, TXT, and PDF formats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic":    {"type": "string", "description": "Research topic"},
                    "summary":  {"type": "string", "description": "Markdown report content"},
                    "sources":  {"type": "array",  "description": "List of source objects"},
                    "metadata": {"type": "object", "description": "Generation metadata"},
                },
                "required": ["topic", "summary", "sources", "metadata"],
            },
        ),
        Tool(
            name="list_reports",
            description="List the most recently saved research reports.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max reports to return", "default": 10}
                },
            },
        ),
        Tool(
            name="read_report",
            description="Read a previously saved report by filename.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "JSON filename of the report"}
                },
                "required": ["filename"],
            },
        ),
    ]


@filesystem_server.call_tool()
async def call_filesystem_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from an MCP client."""
    if name == "save_report":
        result = _do_save_report(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "list_reports":
        result = _do_list_reports(int(arguments.get("limit", 10)))
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "read_report":
        result = _do_read_report(arguments["filename"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    raise ValueError(f"Unknown tool: {name}")


async def run_filesystem_server() -> None:
    """Run the filesystem MCP server over stdio (for standalone use)."""
    async with stdio_server() as (read_stream, write_stream):
        await filesystem_server.run(read_stream, write_stream,
                                    filesystem_server.create_initialization_options())


# ---------------------------------------------------------------------------
# In-process helpers — call these from agent.py
# ---------------------------------------------------------------------------

def save_report_inprocess(topic: str, summary: str, sources: list, metadata: dict) -> dict:
    """Call the save_report MCP tool in-process."""
    logger.info("[%s v%s] save_report_inprocess: '%s'", FILESYSTEM_SERVER_NAME, FILESYSTEM_VERSION, topic)
    return _do_save_report(topic=topic, summary=summary, sources=sources, metadata=metadata)


def list_reports_inprocess(limit: int = 10) -> list:
    """Call the list_reports MCP tool in-process."""
    return _do_list_reports(limit)


# ---------------------------------------------------------------------------
# Internal filesystem implementation
# ---------------------------------------------------------------------------

_REPORTS_DIR = Path("reports")


def _do_save_report(*, topic: str, summary: str, sources: list, metadata: dict) -> dict:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    slug      = _slugify(topic)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix    = f"{slug}_{timestamp}"
    saved: dict[str, str | None] = {}

    # JSON
    json_path = _REPORTS_DIR / f"{prefix}.json"
    json_path.write_text(
        json.dumps({"topic": topic, "summary": summary, "sources": sources,
                    "metadata": metadata, "saved_at": datetime.now().isoformat()},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    saved["json"] = str(json_path.resolve())
    logger.info("[%s] Saved JSON → %s", FILESYSTEM_SERVER_NAME, json_path.name)

    # TXT
    txt_path = _REPORTS_DIR / f"{prefix}.txt"
    txt_path.write_text(_format_txt(topic, summary, sources, metadata), encoding="utf-8")
    saved["txt"] = str(txt_path.resolve())
    logger.info("[%s] Saved TXT  → %s", FILESYSTEM_SERVER_NAME, txt_path.name)

    # PDF
    if PDF_AVAILABLE:
        pdf_path = _REPORTS_DIR / f"{prefix}.pdf"
        _write_pdf(pdf_path, topic, summary, sources, metadata)
        saved["pdf"] = str(pdf_path.resolve())
        logger.info("[%s] Saved PDF  → %s", FILESYSTEM_SERVER_NAME, pdf_path.name)
    else:
        saved["pdf"] = None

    return saved


def _do_list_reports(limit: int) -> list:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports = []
    for f in sorted(_REPORTS_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append({
                "filename": f.name,
                "topic":    data.get("topic", "Unknown"),
                "saved_at": data.get("saved_at", ""),
                "tokens":   data.get("metadata", {}).get("tokens_used", 0),
            })
        except Exception:
            pass
    return reports


def _do_read_report(filename: str) -> dict | None:
    path = _REPORTS_DIR / filename
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:50]


def _format_txt(topic: str, summary: str, sources: list, metadata: dict) -> str:
    sep   = "=" * 62
    lines = [
        "AI RESEARCH ASSISTANT — SAVED REPORT", sep,
        f"Topic     : {topic}",
        f"Generated : {metadata.get('generated_at', '')}",
        f"Model     : {metadata.get('model', '')}",
        f"Tokens    : {metadata.get('tokens_used', '')}",
        f"Elapsed   : {metadata.get('elapsed_sec', '')}s",
        sep, "",
        "\n".join(
            line.lstrip("#").strip() if line.startswith("#") else line
            for line in summary.split("\n")
        ),
        "", sep, "SOURCES", sep,
    ]
    for s in sources:
        lines += [f"• {s['title']}", f"  {s['url']}", f"  {s['snippet'][:120]}...", ""]
    return "\n".join(lines)


def _write_pdf(path: Path, topic: str, summary: str, sources: list, metadata: dict) -> None:
    buf  = BytesIO()
    doc  = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=2*cm,  bottomMargin=2*cm)
    styl = getSampleStyleSheet()
    ts = ParagraphStyle("CT",  parent=styl["Title"],    fontSize=20,
                        textColor=colors.HexColor("#0f172a"), spaceAfter=4)
    ms = ParagraphStyle("CM",  parent=styl["Normal"],   fontSize=9,
                        textColor=colors.HexColor("#64748b"), spaceAfter=10)
    h2 = ParagraphStyle("CH2", parent=styl["Heading2"], fontSize=13,
                        textColor=colors.HexColor("#1d4ed8"), spaceBefore=10, spaceAfter=3)
    bs = ParagraphStyle("CB",  parent=styl["Normal"],   fontSize=10,
                        leading=16, textColor=colors.HexColor("#1e293b"))
    ss = ParagraphStyle("CS",  parent=styl["Normal"],   fontSize=9,
                        leading=13, textColor=colors.HexColor("#334155"))

    story = [
        Paragraph(f"Research Report: {topic}", ts),
        Paragraph(
            f"Generated: {metadata.get('generated_at','')[:10]} &nbsp;|&nbsp; "
            f"Model: {metadata.get('model','')} &nbsp;|&nbsp; "
            f"Tokens: {metadata.get('tokens_used','')}",
            ms,
        ),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")),
        Spacer(1, 0.3*cm),
    ]

    for line in summary.split("\n"):
        s = line.strip()
        if not s:
            story.append(Spacer(1, 0.15*cm))
        elif s.startswith("## "):
            story.append(Paragraph(s[3:], h2))
        elif s.startswith("# "):
            pass
        elif s.startswith(("- ", "* ")):
            story.append(Paragraph(f"&bull; {s[2:]}", bs))
        else:
            story.append(Paragraph(s, bs))

    story += [
        Spacer(1, 0.3*cm),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")),
        Paragraph("Sources Referenced", h2),
    ]
    for s in sources:
        story.append(Paragraph(
            f"&bull; <b>{s['title']}</b><br/>"
            f"<font color='#1d4ed8'>{s['url']}</font><br/>"
            f"<font color='#64748b'>{s['snippet'][:120]}...</font>",
            ss,
        ))
        story.append(Spacer(1, 0.1*cm))

    doc.build(story)
    path.write_bytes(buf.getvalue())
