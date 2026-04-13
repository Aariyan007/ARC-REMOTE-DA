<div align="center">

<!-- HEADER BANNER -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:ff7a00,50:ff9a2f,100:ff7a00&height=200&section=header&text=F.R.I.E.N.D&fontSize=80&fontColor=ffffff&fontAlignY=38&desc=Just%20A%20Rather%20Very%20Intelligent%20System&descAlignY=58&descSize=18&descColor=ffffff&animation=twinkling" />
<br/>

<!-- BADGES -->
![Python](https://img.shields.io/badge/Python-3.10+-ff7a00?style=for-the-badge&logo=python&logoColor=white&labelColor=1a1a1a)
![Gemini](https://img.shields.io/badge/Gemini%201.5%20Flash-LLM%20Brain-ff9a2f?style=for-the-badge&logo=google&logoColor=white&labelColor=1a1a1a)
![Whisper](https://img.shields.io/badge/Whisper-STT-ff7a00?style=for-the-badge&logo=openai&logoColor=white&labelColor=1a1a1a)
![Status](https://img.shields.io/badge/Status-Active%20Development-22c55e?style=for-the-badge&labelColor=1a1a1a)
![Platform](https://img.shields.io/badge/Platform-macOS%20M2-silver?style=for-the-badge&logo=apple&logoColor=white&labelColor=1a1a1a)

<br/>

```
   █████╗ ██████╗  ██████╗
  ██╔══██╗██╔══██╗██╔════╝
  ███████║██████╔╝██║     
  ██╔══██║██╔══██╗██║     
  ██║  ██║██║  ██║╚██████╗
  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝
        A R C   S Y S T E M
```

*"Good morning. I've already reviewed your schedule, pre-loaded your system diagnostics, and optimized your workflow. Shall we begin?"*

</div>

---

## ⚡ Overview

**FRIEND** is a fully local, voice-controlled personal AI assistant built for developers who refuse to settle for Siri. Powered by **Gemini 3.5 preview** as the brain and **OpenAI Whisper** for speech recognition, it understands natural commands, controls your Mac, searches the web, manages memory, and learns your habits over time.

This isn't a toy. It's a system replacement.

> **Codename internally:** `Startup`  
> **Vision:** Replace the need for a mouse/keyboard for 80% of dev workflow

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        JARVIS CORE                          │
├──────────────┬──────────────────────────┬───────────────────┤
│  INPUT LAYER │     INTELLIGENCE LAYER   │   OUTPUT LAYER    │
│              │                          │                   │
│  🎙️ PyAudio  │  🧠 Gemini 1.5 Flash    │  🔊 Mac TTS       │
│  Whisper STT │  (Intent Routing + LLM)  │  (Daniel Voice)   │
│  ECAPA Auth  │  memory.py + logger.py   │  voice_response   │
│  Noise Cal.  │  Gemini-First Routing    │  is_speaking flag │
└──────────────┴──────────────────────────┴───────────────────┘
        │                    │                     │
        ▼                    ▼                     ▼
  speech_to_text.py   intent_router.py      open_apps.py
                       llm_brain.py         web_search.py
                       memory.py            system_actions.py
                                            time_utils.py
```

**No keyword matching. No if-else chains. Every command routes through Gemini.**

---

## 🧩 Module Breakdown

| Module | Status | Description |
|---|---|---|
| `speech_to_text.py` | ✅ Complete | Whisper base model, silence detection, auto noise calibration |
| `intent_router.py` | ✅ Complete | Gemini-first routing — LLM decides what to do |
| `voice_response.py` | ✅ Complete | Mac `say` (Daniel), `is_speaking` flag prevents feedback loops |
| `llm_brain.py` | ✅ Complete | Gemini 1.5 Flash — core reasoning engine |
| `memory.py` | ✅ Complete | Stores facts, context, user history |
| `chat.py` | ✅ Complete | Standalone text chat — `data/users/<name>.json` per user |
| `open_apps.py` | ✅ Complete | Opens any app by voice |
| `web_search.py` | ✅ Complete | Real-time web search on command |
| `time_utils.py` | ✅ Complete | Time/date queries |
| `system_actions.py` | ✅ Complete | System control (sleep, volume, etc.) |
| `logger.py` | ✅ Complete | Full conversation logging |
| `main.py` | ✅ Complete | Master orchestrator — everything wired |
| `mood/` system | 🔄 In Progress | Dynamic mood-aware responses |
| Memory → `main.py` | 🔄 In Progress | Wiring persistent memory into live session |
| Nightly Extractor | 🔄 Planned | Gemini reads convos at midnight, extracts facts |

---

## 🚀 Getting Started

### Prerequisites

- macOS (Apple Silicon M1/M2/M3 recommended)
- Python 3.10+
- [Homebrew](https://brew.sh/) installed
- Gemini API Key (free tier works — 5 req/min)

### Installation

```bash
# Clone the repo
git clone https://github.com/Aariyan007/THEFriend.git
cd THEFriend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your Gemini API Key
export GEMINI_API_KEY="your_key_here"
# Or add it to a .env file

# Run Jarvis
python main.py
```

### First Time Setup

```bash
# Whisper downloads the base model on first run (~150MB)
# Noise calibration happens automatically — stay quiet for 2 seconds
# Say your name when prompted to create your profile
```

---

## 💬 Multi-User: `chat.py`

`chat.py` is a **standalone text interface** — no microphone needed. Teammates can use it on their own machines.

Each user gets their own file:
```
data/
└── users/
    ├── aariyan.json      ← profile + all sessions
    ├── teammate1.json
    └── teammate2.json
```

**Why it exists:**
- Teammates can interact with Jarvis from any device
- Used as a **30-day training pipeline** — daily use exposes Jarvis to slang, habits, and personality before fine-tuning Whisper

```bash
python chat.py
# > Enter your name: Aariyan
# > You: bro open chrome
# > Jarvis: On it.
```

---

## 🖥️ Iron Man HUD Interface

The UI is an **Iron Man-style HUD** with 8 live panels:

```
┌─────────────┬──────────────┬─────────────────┐
│   RADAR     │ VOICE AUTH   │ SYS DIAGNOSTICS │
├─────────────┼──────────────┼─────────────────┤
│ FACE TRACK  │  ARC REACTOR │   BIOMETRICS    │
├─────────────┴──────────────┴─────────────────┤
│           COMMAND LOG                        │
├──────────────────────────────────────────────┤
│   JARVIS BRAIN  (Mood · Gemini · Commands)   │
└──────────────────────────────────────────────┘
```

> UI launch is the **last** step. Everything else gets built first.

---

## 📡 Remote Terminal Mode (ESP32)

**The vision:** Control Jarvis from your college classroom.

```
[Class]                              [Home]
ESP32 + INMP441 mic                  Mac M2
   │                                    │
   │──── audio over WiFi ─────────────▶│
   │                                    │ Full Jarvis pipeline runs
   │◀─── audio response ───────────────│
   │                                    │
   Plays on speaker              Flask server + ngrok
```

**Hardware needed (~₹1350 total):**
| Component | Price |
|---|---|
| ESP32 | ₹950 |
| INMP441 MEMS Mic | ₹200 |
| Small USB Speaker | ₹500 |

---

## 🗺️ Roadmap

### 🔥 Near Term
- [ ] Dynamic Gemini-generated responses (no static replies)
- [ ] Mood system (`mood/` folder) — affect tone based on context
- [ ] Wire `memory.py` into live `main.py` session
- [ ] Nightly extractor — Gemini reads conversation logs at midnight, extracts key facts

### 🚀 Medium Term
- [ ] Email — send, search, read aloud
- [ ] Folder search and creation by voice
- [ ] Face detection + mood detection (small USB camera)
- [ ] Rude / personality mode
- [ ] ESP32 remote terminal from class
- [ ] Screen vision + automation
- [ ] ML habit learning

### 🌐 Long Term
- [ ] Fine-tune Whisper on 30 days of personal chat data
- [ ] Voice cloning
- [ ] Real-time translation
- [ ] Smart home (ESP32 sensors)
- [ ] Meeting mode — auto-summarize, take notes
- [ ] Proactive mode — Jarvis acts without being asked
- [ ] Code assistant with screen vision
- [ ] Face recognition from ID card database
- [ ] Morning briefing (news + calendar + weather)
- [ ] Health monitoring
- [ ] WhatsApp / call integration

---

## 🛠️ Tech Stack

```yaml
Speech-to-Text:   OpenAI Whisper (base, local)
LLM Brain:        Google Gemini 1.5 Flash (free tier → paid later)
Voice Output:     macOS "say" command (Daniel voice)
Mic Input:        PyAudio + silence detection
Voice Auth:       ECAPA speaker verification model
Fuzzy Matching:   rapidfuzz
Data Storage:     JSON (data/users/<name>.json)
Remote Server:    Flask + ngrok (for ESP32 mode)
Hardware:         Mac M2 (primary), ESP32 (remote terminal)
```

---

## 📁 Project Structure

```
THEFriend/
├── main.py                  # Master orchestrator
├── chat.py                  # Standalone text chat
├── requirements.txt
├── .env                     # API keys (gitignored)
│
├── modules/
│   ├── speech_to_text.py    # Whisper STT
│   ├── intent_router.py     # Gemini-first routing
│   ├── voice_response.py    # TTS + feedback prevention
│   ├── llm_brain.py         # Gemini 1.5 Flash
│   ├── memory.py            # Persistent memory
│   ├── logger.py            # Conversation logging
│   ├── open_apps.py         # App control
│   ├── web_search.py        # Web search
│   ├── time_utils.py        # Time queries
│   └── system_actions.py   # System control
│
├── mood/                    # Mood system (WIP)
│
├── data/
│   └── users/               # Per-user JSON profiles
│       └── <name>.json
│
└── ui/                      # Iron Man HUD (built separately)
```

---

## ⚠️ Known Limits

- Gemini free tier: **5 requests/minute** — will upgrade to paid API
- Voice auth (ECAPA) is experimental — may have false accepts in noisy environments
- ESP32 mode requires ngrok tunnel running on Mac

---

## 👤 Author

**Aariyan** — Full Stack Developer · Backend Engineer · AI Builder  
3rd Year BTech CSE @ MITS (KTU)

[![GitHub](https://img.shields.io/badge/GitHub-Aariyan007-ff7a00?style=for-the-badge&logo=github&logoColor=white&labelColor=1a1a1a)](https://github.com/Aariyan007)

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:ff7a00,50:ff9a2f,100:ff7a00&height=100&section=footer" />
*"The thing is, the suit and I are one."*

**⭐ Star this repo if you think AI assistants should be built, not bought.**

</div>
