# ARC Remote — Architecture

> This document covers the internal architecture of ARC Remote. For setup and usage, see the main [README](../README.md).

## What ARC Remote Does

- Pairs a phone or browser client to a desktop daemon with a 6-digit code
- Issues natural-language commands to the desktop over HTTP
- Streams job state back over WebSocket, with HTTP polling fallback
- Asks for clarification or confirmation when a command is ambiguous
- Executes desktop actions through a shared runtime
- Persists jobs and job events to SQLite
- Logs remote activity for auditing

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

## Security Model

The remote path has a few important safety layers:

- device pairing via a one-time 6-digit code
- bearer token auth after pairing
- a command allowlist / dangerous-pattern filter in `remote/allowlist.py`
- audit logging in `remote/security.py`
- per-job persistence in SQLite
- rate limiting on pairing attempts

This is not a full sandbox yet. It is a practical first-pass control plane for a trusted personal setup on a local network or tightly controlled environment.

## Architecture Diagram

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
  README.md               # User-facing setup & usage guide
  docs/ARCHITECTURE.md     # This file
  requirements.txt         # Core dependencies (remote mode)
  requirements-full.txt    # All dependencies (voice + browser + perception)
  setup.sh                 # One-command setup script
  .env.example             # Environment variable template
  main.py                  # Voice entry point (legacy)
  main_ui.py               # Desktop UI entry point
  test_phase1.py           # Smoke tests
  test_phase2.py           # Smoke tests
  core/                    # Shared runtime, routing, workflows, agents, memory, safety
  control/                 # Desktop, browser, file, email, and OS action implementations
  perception/              # OCR, screen capture, browser state, accessibility hooks
  remote/                  # Dispatcher server, auth, allowlist, job store, persistence
  mobileapp/               # Paired client UI (Vite)
  ui/                      # Built frontend output (served by FastAPI)
  data/                    # Runtime data (SQLite, logs)
```

Important directories:

- `remote/` — dispatcher server, auth, allowlist, job store, persistence
- `mobileapp/` — paired client UI source
- `ui/` — built client UI (output of `cd mobileapp && npm run build`)
- `core/` — shared runtime, routing, workflows, agents, memory, safety
- `control/` — desktop, browser, file, email, and OS action implementations
- `perception/` — OCR, screen capture, browser state, accessibility hooks

## API Surface

Main endpoints in the current dispatcher server:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/pair` | Exchange pairing code + device name for a bearer token |
| `GET` | `/pairing-code` | Returns the current pairing code (local testing) |
| `GET` | `/health` | Health and boot status |
| `POST` | `/command` | Submit a command, receive a `job_id` |
| `POST` | `/reply/{job_id}` | Answer a clarify or confirm event |
| `GET` | `/jobs/{job_id}` | Poll job events over HTTP |
| `GET` | `/jobs/health_check_ping` | Token validity check |
| `WS` | `/stream/{job_id}` | Real-time event stream for a job |
| `GET` | `/suggestions` | Dynamic command suggestions |

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
- platform-specific actions are not equally mature
- perception and verification are present but not complete across every action family
- the safety layer is useful, but not yet a hardened multi-tenant sandbox
