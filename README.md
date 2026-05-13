# AI Research Assistant

A production-grade AI agent built with **Groq API (LLaMA-3.3-70B)**, **Gradio**, and **two genuine MCP servers** — Web Search (SerpAPI) and Filesystem. Enter any topic and receive a structured, source-backed research report that is automatically saved to disk.

---

## Architecture

```
User Input (Gradio)
       │
  ResearchAgent          ← orchestrates all stages  (agent.py)
       │
MCP Server #1            ← WebSearchMCPServer        (mcp_services.py)
  web-search-mcp           SerpAPI · Google Search
  Tool: search_web         Falls back to stub results without API key
       │
  Groq API               ← LLaMA-3.3-70B-Versatile  (agent.py)
       │
MCP Server #2            ← FilesystemMCPServer       (mcp_services.py)
  filesystem-mcp           Tools: save_report · list_reports · read_report
  Auto-saves JSON + TXT + PDF to /reports
       │
Gradio UI                ← Report · Sources · Saved Files tabs + Export  (ui.py)
```

---

## Features

| Feature | Detail |
|---|---|
| **LLM** | Groq API — LLaMA-3.3-70B-Versatile (free tier) |
| **MCP Server #1** | `web-search-mcp` — SerpAPI (Google Search), live web context injection |
| **MCP Server #2** | `filesystem-mcp` — auto-saves JSON, TXT, PDF with `save_report` tool |
| **Real MCP Protocol** | Both servers built with the official `mcp` Python SDK; runnable via stdio |
| **Frontend** | Gradio — runs in any browser, no installation required |
| **Session State** | Per-session `gr.State` — no global mutable variables |
| **Report Structure** | Executive Summary → Key Findings → Background → Developments → Applications → Challenges → Outlook |
| **Report Archive** | History panel showing all previously saved reports |
| **Export** | TXT and PDF download buttons (buttons show helpful label when no report yet) |
| **Error Handling** | Empty input, API failures, missing keys — all handled gracefully |
| **Logging** | Timestamped logs for every pipeline stage |

---

## Project Structure

```
ai-intern-final-yourname/
├── mcp_services.py     ← MCP Server #1 (WebSearch) + MCP Server #2 (Filesystem)
├── agent.py            ← ResearchAgent — orchestrates MCP + Groq pipeline
├── ui.py               ← Gradio UI — all frontend logic
├── requirements.txt    ← Python dependencies
├── .env.example        ← API key template (copy to .env and fill in)
├── .env                ← YOUR keys (never commit this file)
├── README.md           ← This file
└── reports/            ← Auto-created; all saved reports live here
    ├── quantum_computing_20260508_143201.json
    ├── quantum_computing_20260508_143201.txt
    └── quantum_computing_20260508_143201.pdf
```

---

## Setup & Run

### Prerequisites
- Python 3.10+
- Free **Groq API key** → [console.groq.com/keys](https://console.groq.com/keys)
- *(Optional)* Free **SerpAPI key** → [serpapi.com](https://serpapi.com) — 100 free searches/month, no credit card required

### Step 1 — Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/ai-intern-final-yourname.git
cd ai-intern-final-yourname
```

### Step 2 — Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Add your API keys

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
SERP_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxx      # optional
```

> **Note:** If `SERP_API_KEY` is omitted, the app uses curated stub search results — you can still test the full pipeline end-to-end without any paid key.

### Step 5 — Run

```bash
python ui.py
```

Open **http://localhost:7860** in your browser.

---

## How to Use

1. Type a research topic in the search box
2. Press **↑** or hit **Enter**
3. Wait ~5–15 seconds for the pipeline to complete
4. Browse the **Report** tab for the full structured report
5. Check the **Sources** tab to see the web sources used
6. Check the **Saved Files** tab to see exactly where files were saved on disk
7. Click **Download TXT** or **Download PDF** to export

---

## MCP Servers — Technical Details

Both servers are built with the official [`mcp`](https://pypi.org/project/mcp/) Python SDK and can be run standalone over stdio transport for any MCP-compatible client (e.g. Claude Desktop, MCP Inspector).

### MCP Server #1 · `web-search-mcp`

| Property | Value |
|---|---|
| Class | `WebSearchMCPServer` |
| Tool | `search_web(query, num_results)` |
| Provider | SerpAPI — Google Search engine |
| Endpoint | `https://serpapi.com/search` |
| Output | `{service, version, query, is_live, results: [{title, url, snippet}]}` |
| Fallback | Curated stub results when `SERP_API_KEY` is absent |

Search results are formatted and injected directly into the LLM system prompt as grounded source context, ensuring every report is anchored to real web data rather than hallucinated facts.

### MCP Server #2 · `filesystem-mcp`

| Property | Value |
|---|---|
| Class | `FilesystemMCPServer` |
| Tools | `save_report`, `list_reports`, `read_report` |
| Storage | `./reports/` (auto-created) |
| Formats | JSON (full record), TXT (plain text), PDF (styled, requires reportlab) |
| Filename | `{topic_slug}_{YYYYMMDD_HHMMSS}.{ext}` |

Every report is automatically saved immediately after generation.

### Running MCP servers standalone (optional)

```bash
# Web Search server over stdio
python -c "import asyncio; from mcp_services import run_web_search_server; asyncio.run(run_web_search_server())"

# Filesystem server over stdio
python -c "import asyncio; from mcp_services import run_filesystem_server; asyncio.run(run_filesystem_server())"
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key for LLaMA-3.3-70B inference |
| `SERP_API_KEY` | Optional | SerpAPI key for live Google Search results |

---

## Dependencies

| Package | Purpose |
|---|---|
| `groq` | Groq API client for LLaMA inference |
| `gradio` | Web UI framework |
| `mcp` | Official MCP Python SDK (builds real MCP servers) |
| `requests` | HTTP calls to SerpAPI |
| `python-dotenv` | `.env` file loading |
| `reportlab` | PDF generation |

Install all at once:

```bash
pip install groq gradio mcp requests python-dotenv reportlab
```

---

## Getting API Keys

**Groq (Free):**
1. Visit [console.groq.com](https://console.groq.com)
2. Sign up → **API Keys** → **Create API Key**
3. Copy the key starting with `gsk_`

**SerpAPI (Free — 100 searches/month, no credit card):**
1. Visit [serpapi.com](https://serpapi.com)
2. Sign up → Dashboard → copy your **API Key**

## Demo Video

Project demonstration video:https://drive.google.com/drive/folders/1EP745cinPG8NZ5cP_uZF4oAxnSW8AeFa
