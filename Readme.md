# 🔍 BugLens — AI Runtime Debugging Platform

Autonomously drives your app in a real browser, catches runtime failures,
and delivers plain-English bug reports — before a single user is affected.

## Architecture

```
L1  Client Interface     →  React / Next.js (not in this repo)
L2  Backend Orchestrator →  Python · FastAPI       ← YOU ARE HERE
L3  Sandbox + Browser    →  Docker · Playwright    ← YOU ARE HERE
L4  AI Analysis Engine   →  Anthropic Claude API   ← YOU ARE HERE
```

## Project Layout

```
buglens/
├── app/
│   ├── main.py              # FastAPI app + lifespan
│   ├── api/
│   │   ├── sessions.py      # POST /sessions — create & run a debug session
│   │   └── reports.py       # GET  /reports/{id} — fetch results
│   ├── core/
│   │   ├── config.py        # Settings (env vars, paths)
│   │   └── logging.py       # Structured logger
│   ├── models/
│   │   ├── session.py       # Session / status data models
│   │   └── report.py        # BugReport / DisasterScore models
│   └── services/
│       ├── sandbox.py       # Unzip, detect framework, boot dev server
│       ├── browser.py       # Playwright agent — explore, interact, capture
│       └── analyzer.py      # Claude API — map evidence → bug reports
├── workspaces/              # Temp dirs per session (git-ignored)
├── requirements.txt
├── .env.example
└── README.md
```

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright browsers
playwright install chromium

# 3. Copy and fill in env vars
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env

# 4. Run the API server
uvicorn app.main:app --reload --port 8000
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions` | Upload a ZIP, start a debug run |
| GET | `/sessions/{id}` | Poll session status + live log |
| GET | `/reports/{id}` | Fetch completed bug report |
| DELETE | `/sessions/{id}` | Clean up workspace |

## How a Session Works

1. **Upload** — client POSTs a `.zip` of their React/Next.js/Vite app
2. **Sandbox** — server unzips, detects framework, runs `npm install && npm run dev`
3. **Explore** — Playwright crawls every route, maps all clickable elements
4. **Capture** — agent clicks, fills forms, submits — records JS errors, failed requests, hydration issues, dead UI
5. **Report** — Claude receives all evidence and writes structured bug reports with Disaster Scores

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | required |
| `WORKSPACE_DIR` | Where sessions are stored | `./workspaces` |
| `MAX_ROUTES` | Max routes to explore per session | `20` |
| `MAX_ACTIONS_PER_ROUTE` | Max interactions per route | `15` |
| `DEV_SERVER_TIMEOUT` | Seconds to wait for server boot | `60` |
| `ANTHROPIC_MODEL` | Claude model to use | `claude-sonnet-4-20250514` |