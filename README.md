<p align="center">
  <img src="ui/favicon.svg" width="80" alt="ARC Remote Logo" />
</p>

<h1 align="center">ARC Remote</h1>

<p align="center">
  <strong>Control your desktop from your phone using natural language.</strong>
  <br />
  Open source · Runs locally · No cloud required
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#what-it-does">What It Does</a> ·
  <a href="#example-commands">Example Commands</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a>
</p>

---

## What It Does

ARC Remote turns your Mac into a remotely-controllable desktop agent. Send natural language commands from your phone, and your computer executes them — opening apps, finding files, sending emails, browsing the web, and more.

```
📱 Phone: "find my resume and email it to john@example.com"
      ↓
🖥️ Desktop: finds the file, opens Gmail, attaches it, drafts the email
      ↓
📱 Phone: shows real-time progress → asks for confirmation → sends
```

**How it works:**

1. Your Mac runs a local server (the ARC daemon)
2. You open the web app on your phone (same WiFi)
3. Pair with a one-time 6-digit code
4. Send commands — your desktop does the work
5. Get real-time progress, clarifications, and results on your phone

No data leaves your local network. Your commands are processed by your own machine.

## Quick Start

### Prerequisites

- **macOS** (Windows support coming soon)
- **Python 3.9+**
- **Node.js 16+**
- **A free [Gemini API key](https://aistudio.google.com/apikey)** (used for AI intent classification)

### 1. Clone and setup

```bash
git clone https://github.com/Aariyan007/ARC-REMOTE-DA.git
cd ARC-REMOTE-DA
chmod +x setup.sh
./setup.sh
```

The setup script will:
- Create a Python virtual environment
- Install all dependencies
- Build the mobile UI
- Create a `.env` file for your API key

### 2. Add your API key

```bash
# Edit .env and add your Gemini API key
nano .env
```

```
API_KEY=your_gemini_api_key_here
```

### 3. Start the server

```bash
source venv/bin/activate
python -m remote.server          # listens on 127.0.0.1:8000 by default
```

The daemon prints a **pairing code and QR code** in the terminal. Run `python -m remote.pair` any time for a fresh one (single use, 5 minutes). The code is never served over HTTP.

### 4. Reach your Mac from your phone (free)

The server binds to loopback by default, so nothing is exposed until you choose how. Recommended — **Tailscale** (free Personal plan, encrypted, works away from home Wi-Fi):

1. Install Tailscale on the Mac and the phone and sign in to the same account.
2. On the Mac: `tailscale serve --bg 8000` — this gives you `https://<mac-name>.<tailnet>.ts.net`.
3. Set `ARC_PUBLIC_URL=https://<mac-name>.<tailnet>.ts.net` in `.env` so the QR points at it.

Same Wi-Fi only (no Tailscale): `ARC_HOST=0.0.0.0` and `ARC_PUBLIC_URL=http://<mac-lan-ip>:8000`. This is plain HTTP — fine on a trusted home network, not elsewhere.

### 5. Connect your phone

- **Mobile app (recommended):** build it from `mobileapp/` (see [mobileapp/README.md](mobileapp/README.md)), open it, tap **Scan QR code**, and scan the terminal QR.
- **Browser:** open the server URL on your phone and enter the 6-digit code. Use "Add to Home Screen" for an app-like icon.

Manage paired phones with `GET /devices` and revoke one with `DELETE /devices/{id}`; a revoked phone is signed out immediately.

## Example Commands

| Command | What happens |
|---------|-------------|
| `open chrome` | Opens Google Chrome |
| `find resume.pdf` | Searches your files and shows results |
| `take a screenshot` | Captures your screen |
| `send an email to john@example.com` | Opens Gmail and starts composing |
| `open youtube` | Opens YouTube in the browser |
| `volume up` | Increases system volume |
| `what time is it` | Tells you the current time |
| `lock screen` | Locks your Mac |
| `search for tax documents` | Finds files matching your query |
| `what can you do` | Shows available capabilities |

When a command is ambiguous, ARC will ask you for clarification through your phone before proceeding.

## Supported Platforms

| | Status |
|---|--------|
| **Desktop: macOS** | ✅ Supported |
| **Desktop: Windows** | 🔜 Coming soon |
| **Desktop: Linux** | 🔜 Coming soon |
| **Phone: Any browser** | ✅ Works as PWA |
| **Phone: iOS / Android app** | 🧪 Capacitor project (build it yourself — see `mobileapp/README.md`) |

## How It Works

```
┌──────────────┐         ┌──────────────────────────┐
│  Your Phone  │         │  Your Mac                │
│              │         │                          │
│  Web App     │── HTTP ─│  ARC Daemon (FastAPI)    │
│  (PWA)       │         │    ├─ Intent Router      │
│              │◀── WS ──│    ├─ Action Engine       │
│  Pairing     │         │    ├─ Job Manager         │
│  Commands    │         │    └─ Desktop Automation   │
│  Results     │         │                          │
└──────────────┘         └──────────────────────────┘
     same WiFi network
```

1. **Submit** — Your phone sends a natural language command
2. **Route** — The AI classifies your intent and picks the right action
3. **Execute** — Your Mac performs the action (open app, find file, etc.)
4. **Stream** — Real-time progress streams back to your phone via WebSocket
5. **Clarify** — If something is ambiguous, it asks before proceeding
6. **Result** — Final result appears on your phone

## Project Structure

```
ARC-REMOTE-DA/
├── remote/          # Server: FastAPI daemon, auth, job store
├── core/            # AI brain: intent routing, workflows, agents
├── control/         # Actions: browser, email, files, system
├── perception/      # Screen capture, OCR, accessibility
├── mobileapp/       # Phone UI source (Vite)
├── ui/              # Built phone UI (served by server)
├── setup.sh         # One-command setup
├── .env.example     # Environment template
└── requirements.txt # Python dependencies
```

For detailed architecture docs, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Optional Features

### Browser Automation (Playwright)

For commands like "open chrome" or "go to youtube":

```bash
pip install playwright>=1.49.0
playwright install chrome
```

### Voice Mode

ARC also supports a voice-activated mode (separate from the phone remote):

```bash
pip install -r requirements-full.txt
python main.py
```

This requires a microphone and additional dependencies (torch, speechbrain, etc).

## Security

- **Private by default** — the daemon listens on loopback; you opt in to LAN or Tailscale exposure
- **One-time pairing** — 6-digit codes are single-use, expire after 5 minutes, are compared in constant time, and 5 wrong guesses lock the client out for 15 minutes. The code is only shown on the desktop (terminal / QR), never over the network
- **Device tokens** — signed, 30-day, bound to a registered device, revocable at any time; the signing key persists in `data/.secret` (mode 600)
- **WebSocket tickets** — streams authenticate with a 30-second one-time ticket, so tokens never appear in URLs or logs
- **Job isolation** — a device can only see, answer or cancel its own jobs
- **Confirmations** — destructive actions require an explicit confirm bound to a per-prompt nonce
- **Command validation, concurrency caps, and per-job timeouts**
- **Audit log** — commands, results, pairing attempts, lockouts, replies and revocations (SQLite, pruned after 30 days)

This is a personal-use control plane, not a multi-tenant sandbox: anyone holding a paired phone can drive your Mac within the confirmation rules.

## Development

### Frontend development

```bash
cd mobileapp
npm run dev -- --host
```

This starts Vite with hot reload and proxies API calls to `localhost:8000`.

### Run tests

```bash
pip install -r requirements-dev.txt
python -m pytest                 # server tests (runtime is stubbed; no ML stack needed)
cd mobileapp && npm test         # client unit tests
```

`tests/manual/` holds the older desktop smoke scripts (need macOS + the full dependencies).

### Build frontend for production

```bash
cd mobileapp
npm run build   # outputs to ../ui/ (served by the daemon and bundled into the apps)
```

## Contributing

Contributions are welcome! Here's how:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run the tests (`python -m pytest` and `cd mobileapp && npm test`)
5. Commit and push (`git push origin feature/my-feature`)
6. Open a Pull Request

## License

MIT

---

<p align="center">
  Built by <a href="https://github.com/Aariyan007">@Aariyan007</a>
</p>
