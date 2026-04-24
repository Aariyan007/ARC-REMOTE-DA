# ARC Remote

ARC Remote is a dispatcher-style desktop automation system.

Think of the product direction as "Claude Dispatcher for your own machine": a paired client submits natural-language jobs, the desktop runtime executes them locally, and the client stays in the loop through live job events, clarification prompts, and confirmations.

This repo is currently a mix of:

- the newer remote dispatcher stack
- a shared desktop automation runtime
- older voice-first ARC/Jarvis code that still powers some execution paths

The dispatcher path is the part to build around.

## What ARC Remote Does

- Pairs a phone or browser client to a desktop daemon with a 6-digit code
- Issues natural-language commands to the desktop over HTTP
- Streams job state back over WebSocket, with HTTP polling fallback
- Asks for clarification or confirmation when a command is ambiguous
- Executes desktop actions through a shared runtime
- Persists jobs and job events to SQLite
- Logs remote activity for auditing

The current repo already contains the core dispatcher loop:

`pair -> submit job -> ack -> clarify/confirm -> execute -> verify -> result`

## Current Product Shape

The remote flow in this repo is centered on:

- `remote/server.py`
  FastAPI daemon for pairing, auth, job submission, replies, polling, and event streaming.
- `core/runtime.py`
  Shared boot + execution entry point used by both the remote server and older voice entry points.
- `remote/job_store.py`
  In-memory job state, event queueing, and blocking user-reply handoff for multi-step jobs.
- `remote/db.py`
  SQLite persistence for jobs and events.
- `mobileapp/`
  Vite-based paired client with a pairing screen, command input, event timeline, and reply UI.

This makes the system closer to a dispatcher/orchestrator than a single-turn assistant:

- the client submits work
- the server assigns a job ID immediately
- the runtime keeps working after the request returns
- the UI watches the job stream
- the user only steps in when the runtime needs a decision

## What It Can Do Today

The exact behavior still depends on environment and installed integrations, but the repo is already set up for:

- file search and file-open flows
- find-and-send / find-and-email style workflows
- browser automation through Playwright
- Gmail draft / attachment automation
- desktop actions such as opening apps, switching apps, file operations, and basic system controls
- clarification and confirmation prompts inside the remote job flow
- optional voice, OCR, perception, and accessibility-based subsystems

Some code paths still use the older `Jarvis` naming internally. The current product direction and docs should be treated as `ARC Remote`.

## Dispatcher Flow

1. Start the desktop daemon.
2. Pair a client using the short-lived 6-digit code.
3. Submit a command like `find resume.pdf and send it to me@example.com`.
4. Receive a `job_id` immediately.
5. Subscribe to the job stream.
6. If the runtime needs input, it emits `clarify` or `confirm`.
7. The client replies with `/reply/{job_id}`.
8. The job ends with `result` or `error`.

Event types currently used in the repo:

- `ack`
- `clarify`
- `confirm`
- `progress`
- `executing`
- `verify`
- `result`
- `error`

## Security Model Right Now

The remote path has a few important safety layers already:

- device pairing via a one-time 6-digit code
- bearer token auth after pairing
- a command allowlist / dangerous-pattern filter in `remote/allowlist.py`
- audit logging in `remote/security.py`
- per-job persistence in SQLite

This is not a full sandbox yet. It is a practical first-pass control plane for a trusted personal setup on a local network or tightly controlled environment.

## Architecture

```text
mobile client
  -> pair with 6-digit code
  -> POST /command
  -> WS /stream/{job_id}
  -> POST /reply/{job_id}

remote/server.py
  -> auth + allowlist + audit log
  -> enqueue command
  -> persistent worker thread

core/runtime.py
  -> boot shared actions / agents / subsystems
  -> execute_text_command(...)
  -> workflow engine or intent router

job state
  -> remote/job_store.py
  -> remote/db.py
  -> data/remote.db
```

## Project Layout

```text
ARC-REMOTE-DA/
  README.md
  requirements.txt
  main.py
  main_ui.py
  test_phase1.py
  test_phase2.py
  core/
  control/
  perception/
  remote/
  actions/
  mobileapp/
  data/
```

Important directories:

- `remote/` - dispatcher server, auth, allowlist, job store, persistence
- `mobileapp/` - paired client UI
- `core/` - shared runtime, routing, workflows, agents, memory, safety
- `control/` - desktop, browser, file, email, and OS action implementations
- `perception/` - OCR, screen capture, browser state, accessibility hooks

## Local Development

### Backend

Create a virtual environment and install the Python dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install fastapi uvicorn pyjwt
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install fastapi uvicorn pyjwt
```

If you want browser automation:

```bash
playwright install chrome
```

### Frontend

```bash
cd mobileapp
npm install
```

### Environment

Common environment variables used by the repo:

```bash
API_KEY=your_gemini_api_key
ARC_SECRET_KEY=your_stable_jwt_secret
```

Notes:

- `API_KEY` is used by Gemini-backed extraction / planning paths.
- `ARC_SECRET_KEY` is strongly recommended so device tokens stay stable across restarts.

## Running The Dispatcher

Start the desktop daemon:

```bash
python -m uvicorn remote.server:app --host 0.0.0.0 --port 8000
```

You should see ARC print a fresh pairing code in the terminal.

Then start the client:

```bash
cd mobileapp
npm run dev -- --host
```

Open the Vite URL on your phone or desktop browser, enter the pairing code, and submit commands.

## Production-ish Single-Port Setup

If you build the frontend first, `remote/server.py` will serve `mobileapp/dist` directly:

```bash
cd mobileapp
npm run build
cd ..
python -m uvicorn remote.server:app --host 0.0.0.0 --port 8000
```

## API Surface

Main endpoints in the current dispatcher server:

- `POST /pair`
  Exchange pairing code + device name for a bearer token.
- `GET /pairing-code`
  Returns the current pairing code for local testing.
- `GET /health`
  Health and boot status.
- `POST /command`
  Submit a command and receive a `job_id`.
- `POST /reply/{job_id}`
  Answer a clarify or confirm event for a running job.
- `GET /jobs/{job_id}`
  Poll job events over HTTP.
- `GET /jobs/health_check_ping`
  Authenticated token validity check for the client.
- `WS /stream/{job_id}`
  Real-time event stream for a job.

## Example Commands

- `find resume.pdf and send it to me@example.com`
- `find invoice and open it`
- `open chrome and go to github.com`
- `turn the volume up`
- `open gmail`
- `search for my latest tax file`

When the runtime cannot safely continue, it should ask instead of guessing.

## Gmail / Browser Automation Notes

The browser automation layer uses a persistent Chrome profile so you do not need to hardcode account passwords in the repo.

The current Playwright setup stores profile data under:

```text
~/.friend/chrome_profile
```

Typical first-time flow:

1. Start ARC Remote.
2. Trigger a browser or Gmail command.
3. Log into Gmail manually in the opened Chrome window once.
4. Reuse that session on later runs.

## Tests

The repo currently includes two smoke-style test scripts:

```bash
python test_phase1.py
python test_phase2.py
```

They focus on:

- perception / accessibility degradation behavior
- runtime boot
- fast intent cold start
- verifier fail-closed behavior

## Current Reality

What is solid enough to build on:

- the remote daemon
- the paired client flow
- job IDs and job-event streaming
- reply-driven clarification / confirmation
- shared runtime execution
- audit log and SQLite persistence

What is still in-progress or uneven:

- some legacy voice-first architecture is still mixed into the repo
- environment setup is still a little manual
- platform-specific actions are not equally mature
- perception and verification are present but not complete across every action family
- the safety layer is useful, but not yet a hardened multi-tenant sandbox

## Direction

The repo should keep moving toward a clean dispatcher architecture:

- remote-first control plane
- explicit job lifecycle
- better execution verification
- stronger human-in-the-loop recovery
- clearer separation between dispatcher, runtime, and action workers

That is the right frame for this project now.
