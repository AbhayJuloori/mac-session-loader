# Mac Session Loader

A self-hosted dashboard for scheduling and monitoring [Claude Code](https://claude.ai/code) and [Codex](https://openai.com/codex) AI sessions on macOS — accessible from your phone via Tailscale.

Think of it as an **alarm clock for your AI coding sessions**: set a time, and it warms up a session with a prompt automatically so it's ready when you sit down.

![Dashboard screenshot](docs/screenshot.png)

---

## Features

- **Session scheduler** — set jobs to fire at specific times; sends a warmup prompt to an existing session or creates a new one if needed
- **Real-time status** — pgrep-based detection of actual running `claude`/`codex` processes (not just tmux window existence)
- **Rate limit tracker** — Claude reset time auto-detected from `~/.claude/rate-limit-state.json`; Codex timer manually set via dashboard
- **Usage bar** — % consumed / remaining from Claude's rate-limit state file
- **Idle cleanup** — background cron kills sessions idle past a configurable timeout
- **Session history** — persistent JSON log of all runs with atomic writes
- **Mobile access** — Tailscale Serve exposes the dashboard to your phone over VPN
- **API key auth** — all endpoints require `x-api-key` header
- **ttyd terminal embed** *(optional)* — browser terminal for each session if `ttyd` is installed

---

## Architecture

```
mac-session-loader/
├── backend/
│   ├── main.py          # FastAPI app, lifespan, router wiring
│   ├── scheduler.py     # APScheduler — job execution + idle cleanup cron
│   ├── session.py       # tmux session management, pgrep detection, ttyd
│   ├── storage.py       # Atomic JSON reads/writes with threading.Lock
│   ├── auth.py          # x-api-key dependency
│   ├── models.py        # Pydantic request/response models
│   └── routers/
│       ├── run.py       # POST /run — fire a session/prompt immediately
│       ├── status.py    # GET /status — session state + rate limits
│       ├── jobs.py      # CRUD for scheduled jobs
│       ├── history.py   # GET /history — run log
│       └── system.py    # GET /system — dependency checks
├── frontend/
│   ├── index.html       # Single-page dashboard
│   ├── app.js           # Vanilla JS, no build step
│   └── style.css
├── tests/               # 60 pytest tests
├── start.sh             # Production start (caffeinate + uvicorn)
├── start-dev.sh         # Dev start (--reload)
└── .env.example         # Environment variable template
```

**Stack:** FastAPI · APScheduler · tmux · Vanilla JS · Python 3.9+

No external database — state is stored in local JSON files (`history.json`, `jobs.json`, `expiry.json`).

---

## Prerequisites

- macOS (uses `tmux`, `pgrep`, `launchd`)
- Python 3.9+
- `tmux` — `brew install tmux`
- Claude Code CLI and/or Codex CLI installed and authenticated
- [Tailscale](https://tailscale.com) *(optional, for phone access)*
- `ttyd` — `brew install ttyd` *(optional, for browser terminal)*

---

## Quick Start

```bash
git clone https://github.com/AbhayJuloori/mac-session-loader.git
cd mac-session-loader

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set SESSION_LOADER_KEY to a secret string

./start-dev.sh         # Dev mode with auto-reload
# or
./start.sh             # Production (binds 127.0.0.1:8080)
```

Open `http://127.0.0.1:8080` in your browser.

All API calls require the header `x-api-key: <your SESSION_LOADER_KEY>`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SESSION_LOADER_KEY` | *(required)* | API key for all endpoints |
| `DATA_DIR` | `.` | Directory for JSON state files |
| `CLAUDE_COMMAND` | `claude` | Claude CLI binary name |
| `CODEX_COMMAND` | `codex` | Codex CLI binary name |
| `DEFAULT_WORKSPACE` | `/Users/<you>/` | Default tmux working directory |
| `DEFAULT_TIMEZONE` | `America/New_York` | Scheduler timezone |
| `SESSION_IDLE_TIMEOUT_HOURS` | `6.0` | Hours before idle session is killed (0 = disabled) |
| `SESSION_CLEANUP_INTERVAL_MINUTES` | `10` | How often to run idle cleanup (0 = disabled) |

---

## Auto-Start with launchd

To have the server start automatically at login, create a launchd plist. A template is provided at `launchd/com.yourname.session-loader.plist.example` — copy it, fill in your paths and API key, then load it:

```bash
cp launchd/com.yourname.session-loader.plist.example \
   ~/Library/LaunchAgents/com.yourname.session-loader.plist

# Edit the plist — update WorkingDirectory, API key, and python path

launchctl load ~/Library/LaunchAgents/com.yourname.session-loader.plist

# Check logs
tail -f /tmp/session-loader.log
```

---

## Tailscale Phone Access

```bash
# Install Tailscale, then:
tailscale serve --bg 8080
```

Access the dashboard from your phone at `http://<your-tailscale-ip>:8080`. Get your IP from `tailscale ip -4`.

---

## Tests

```bash
python3 -m pytest tests/ -q     # 60 tests
```

---

## How It Works

**Scheduler flow** (`scheduler.py → _run_job`):
1. Job fires at scheduled time
2. `is_running(session_name)` → if session active, send warmup prompt directly → status `warmed_existing`
3. If session inactive → `start_session(...)` creates a new tmux session, fires warmup async → status `started`

**Rate limit detection:**
- Claude: reads `~/.claude/rate-limit-state.json` — same file Claude Code writes; gives accurate reset time + usage %
- Codex: no local equivalent exists; set expiry manually via dashboard

**Session detection:** uses `pgrep -f <command>` rather than checking tmux window existence — ensures you're detecting a live process, not a dead window.

---

## Forking / Adapting

The core is intentionally minimal. Common customizations:

- **Add a new session type** — extend `session.py` with a new command, add a route in `routers/run.py`
- **Persistent storage** — swap `storage.py` for SQLite or Postgres (Pydantic models are already defined)
- **Auth** — swap the x-api-key in `auth.py` for OAuth if exposing outside Tailscale
- **Notifications** — add a webhook call in `scheduler.py` after a job completes
- **Rate limit for other tools** — add a parser in `routers/status.py` alongside the Claude one

---

## License

MIT
