<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:ff7a00,50:ff9a2f,100:ff7a00&height=200&section=header&text=ARC&fontSize=86&fontColor=ffffff&fontAlignY=38&desc=AI-Operated%20Computer&descAlignY=58&descSize=18&descColor=ffffff&animation=twinkling" />
<br/>

![Python](https://img.shields.io/badge/Python-3.10+-ff7a00?style=for-the-badge&logo=python&logoColor=white&labelColor=1a1a1a)
![Gemini](https://img.shields.io/badge/Gemini-3.1%20Flash%20Lite-ff9a2f?style=for-the-badge&logo=google&logoColor=white&labelColor=1a1a1a)
![Whisper](https://img.shields.io/badge/Whisper-STT-ff7a00?style=for-the-badge&logo=openai&logoColor=white&labelColor=1a1a1a)
![Platform](https://img.shields.io/badge/Platform-macOS%20First-silver?style=for-the-badge&logo=apple&logoColor=white&labelColor=1a1a1a)
![Status](https://img.shields.io/badge/Status-Active%20Development-22c55e?style=for-the-badge&labelColor=1a1a1a)

```text
   █████╗ ██████╗  ██████╗
  ██╔══██╗██╔══██╗██╔════╝
  ███████║██████╔╝██║
  ██╔══██║██╔══██╗██║
  ██║  ██║██║  ██║╚██████╗
  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝
        A R C   S Y S T E M
```

*Build the computer that can actually understand, operate, verify, and recover.*

</div>

---

## Overview

**ARC** is a local-first voice assistant for operating your computer like an AI-controlled system, not just a chatbot with tools. It is built around a deterministic execution loop:

`normalize -> interpret -> clarify -> execute -> verify -> respond -> learn`

The focus is not just “talk to the computer.” The goal is:

- better command grounding
- better OS control
- stronger verification
- fewer fake confirmations
- a path to perception-driven desktop automation

Some older internals and prompts still use the legacy `Jarvis` name, but the product name is **ARC**.

---

## Current Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│                               ARC                                  │
├────────────────┬───────────────────────────────┬───────────────────┤
│ INPUT          │ INTELLIGENCE                  │ OUTPUT            │
│                │                               │                   │
│ Whisper STT    │ fast_intent.py               │ macOS say TTS     │
│ PyAudio        │ command_interpreter.py       │ response_policy   │
│ Wake word      │ intent_router.py             │ logger.py         │
│ Voice auth     │ safety.py                    │ grounded results  │
│                │ action_verifier.py           │                   │
│                │ working_memory.py            │                   │
│                │ manager_agent.py             │                   │
└────────────────┴───────────────────────────────┴───────────────────┘
                         │
                         ▼
                 perception_engine.py
                 browser_state.py
                 screen_capture.py
                 ocr.py
                 ui_accessibility.py
```

### What is already true

- Commands no longer rely on one fragmented response path.
- User-facing action speech is deterministic and grounded in actual outcomes.
- The live router now calls the structured interpreter.
- Missing parameters trigger clarification instead of blind guessing.
- Post-action verification exists for part of the runtime.
- Startup now degrades more gracefully when optional dependencies are missing.

### What is still being built

- deeper browser verification
- full file verification
- accessibility-tree grounding
- richer short-term memory
- messy-command eval datasets

---

## What ARC Can Do Today

- Open, close, switch, and minimize apps.
- Create, edit, rename, copy, and delete files.
- Search the web and open URLs.
- Handle direct system controls like volume, brightness, screenshot, and lock.
- Use a cleaner response loop: `ack -> execute -> verify -> speak result`.
- Ask better follow-up questions when command parameters are missing.
- Run a manager/orchestrator path for more complex multi-step commands.

### Big improvement already shipped

ARC now behaves much less like:

`"I heard something, let me guess and say something cool."`

And much more like:

`"I know what action this is, I know what is missing, I will do it, then I will confirm what actually happened."`

---

## Repository Layout

```text
Startup/
├── main.py
├── chat.py
├── requirements.txt
├── README.md
│
├── core/
│   ├── intent_router.py
│   ├── command_interpreter.py
│   ├── command_schema.py
│   ├── response_policy.py
│   ├── action_result.py
│   ├── action_verifier.py
│   ├── voice_response.py
│   ├── speech_to_text.py
│   ├── fast_intent.py
│   ├── working_memory.py
│   ├── llm_brain.py
│   └── agents/
│
├── control/
│   ├── mac/
│   ├── windows/
│   ├── playwright_browser.py
│   └── web_search.py
│
├── perception/
│   ├── browser_state.py
│   ├── screen_capture.py
│   ├── ocr.py
│   └── ui_accessibility.py
│
├── evals/
│   ├── command_benchmark.json
│   └── run_command_eval.py
│
├── data/
├── ui/
└── _archive/
```

---

## Getting Started

### Prerequisites

- macOS is the primary target right now
- Python 3.10+
- Homebrew recommended
- Gemini API key for fallback/planning flows

### Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment

Set your Gemini key in the shell or in `.env`:

```bash
export API_KEY="your_key_here"
```

### Optional system dependencies

These improve functionality but are not required for every code path:

```bash
brew install tesseract
brew install ffmpeg
```

### Run

```bash
python3 main.py
```

If some optional dependencies are missing, ARC should now fail more cleanly and tell you what needs to be installed instead of crashing immediately on import.

---

## Testing

### Quick module checks

```bash
python3 -m core.response_policy
python3 -m core.action_result
```

### Intent benchmark

```bash
python3 evals/run_command_eval.py
```

### Smoke tests to try manually

- `open chrome`
- `what time is it`
- `create a file`
- `rename it to ideas`
- `open url`
- `volume up`

What you should observe:

- fast ack
- action executes
- grounded result is spoken
- missing info triggers a focused clarification question

---

## Roadmap

### Done

- Centralized response system
- Structured action result layer
- Mac-say response flow
- Live structured interpreter wiring
- Initial action verification hooks
- Better startup dependency handling

### Next priorities

1. Finish action verification for files, browser, and desktop actions
2. Make accessibility and OCR first-class perception inputs
3. Expand working memory for tabs, clipboard, selected items, and task chains
4. Build real messy-command and ambiguity eval datasets
5. Improve browser automation depth to make ARC stronger than OpenClaw on OS control quality

### Long-term goal

Beat broad assistant platforms by being narrower and better:

- better command grounding
- better clarification
- better verification
- better desktop control

---

## Known Limits

- Some optional dependencies are still environment-sensitive.
- macOS is the best-supported platform today.
- `ui_accessibility.py` is still a placeholder, not full native grounding yet.
- `run_command_eval.py --no-init` still needs improvement if you want a truly lightweight no-embedding smoke mode.
- The perception stack exists, but it is not yet complete enough to claim full screen-aware control.

---

## Why This Project Exists

Most assistants stop at:

- answer a question
- call one tool
- say something polished

ARC is trying to go further:

- understand casual commands
- ask the right clarification
- operate the machine
- verify the result
- recover if it fails

That is the difference between a voice chatbot and an AI-operated computer.

---

## Author

**Aariyan**  
Backend Engineer · AI Builder · Full Stack Developer

[![GitHub](https://img.shields.io/badge/GitHub-Aariyan007-ff7a00?style=for-the-badge&logo=github&logoColor=white&labelColor=1a1a1a)](https://github.com/Aariyan007)

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:ff7a00,50:ff9a2f,100:ff7a00&height=100&section=footer" />

**ARC is not meant to sound smart. It is meant to control the computer well.**

</div>
