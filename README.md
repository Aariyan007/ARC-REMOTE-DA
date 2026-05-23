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
python -m uvicorn remote.server:app --host 0.0.0.0 --port 8000
```

You'll see a **QR code** in your terminal — scan it with your phone.

### 4. Connect your phone

1. Scan the QR code (or open the URL shown in terminal)
2. Enter the 6-digit pairing code displayed in the terminal
3. Start sending commands!

**Pro tip:** Tap "Add to Home Screen" in your phone's browser to make it feel like a native app.

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
| **Phone: iOS app** | 🔜 Planned |
| **Phone: Android app** | 🔜 Planned |

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

- **Local only** — Everything runs on your machine, on your local network
- **One-time pairing** — 6-digit codes expire after 5 minutes and single use
- **Token auth** — After pairing, all requests use a signed bearer token
- **Command filtering** — Dangerous commands are blocked by an allowlist
- **Audit log** — All commands are logged locally

## Development

### Frontend development

```bash
cd mobileapp
npm run dev -- --host
```

This starts Vite with hot reload and proxies API calls to `localhost:8000`.

### Run tests

```bash
python test_phase1.py
python test_phase2.py
```

### Build frontend for production

```bash
cd mobileapp
npm run build   # outputs to ../ui/
```

## Contributing

Contributions are welcome! Here's how:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run the tests (`python test_phase1.py && python test_phase2.py`)
5. Commit and push (`git push origin feature/my-feature`)
6. Open a Pull Request

## License

MIT

---

<p align="center">
  Built by <a href="https://github.com/Aariyan007">@Aariyan007</a>
</p>
