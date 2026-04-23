# ARC - Remote Desktop Assistant 🤖

ARC is a powerful, voice-enabled remote desktop orchestration engine. It allows you to find files, draft emails, and perform complex desktop tasks through natural language commands from your mobile device or desktop UI.

## 🚀 Recent Breakthroughs (Today's Progress)

We have successfully stabilized the **"Find and Send"** end-to-end orchestration loop. The system can now:
1.  **Advanced File Search**: Search your local filesystem for specific documents (e.g., "find doc1wire.pdf").
2.  **Smart Disambiguation**: If multiple files match, Jarvis asks you to pick the right one in the UI.
3.  **Rich Confirmation**: Shows a detailed confirmation card with the resolved file path before proceeding.
4.  **Playwright Automation**: Automatically opens Gmail, attaches the local file using a hardened dual-strategy approach, and **auto-sends** the email using `Ctrl+Enter`.
5.  **Clean Exit**: Automatically closes the Gmail browser window once the email is successfully sent.

---

## 🛠 Setup & Requirements

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **Google Chrome**: Installed on the system.

### 2. Environment Variables
Create a `.env` file in the root directory (or set them in your shell):
```bash
API_KEY=your_gemini_api_key
```

### 3. Playwright Installation
The automation layer uses Playwright. You must install the chrome channel:
```bash
pip install playwright
playwright install chrome
```

### 4. Email & Browser Setup (Crucial)
ARC uses a **persistent browser profile** to maintain your login sessions. You do **not** need to provide Gmail passwords in the code.
- **Persistent Profile Path**: `~/.friend/chrome_profile` (created automatically).
- **One-Time Login**: 
    1. Start the ARC backend.
    2. Trigger an email command (e.g., "Open Gmail").
    3. When the Chrome window appears, manually log into your Gmail account.
    4. Playwright will remember this session forever. ARC can then send emails autonomously without asking for credentials again.

---

## 🏃 How to Run

### Step 1: Start the Backend (Uvicorn)
From the root directory:
```bash
uvicorn remote.server:app --port 8000
```
- This will generate a **6-digit pairing code**.
- It starts the PerceptionEngine and the Multi-Agent system.

### Step 2: Start the Frontend (Vite)
Navigate to the mobile app directory:
```bash
cd mobileapp
npm install
npm run dev -- --host
```
- Open the URL in your mobile browser or desktop.
- Enter the pairing code from the backend console.

---

## 🏗 Key Components

- `remote/server.py`: FastAPI server handling WebSockets and UI requests.
- `control/playwright_browser.py`: The "brain" of browser automation. Handles Gmail navigation, file attachment, and auto-sending.
- `control/email_control.py`: High-level orchestration for finding files and routing them to Gmail.
- `control/file_search.py`: Advanced local file searching logic.
- `mobileapp/`: React-based UI with rich status tracking and confirmation prompts.

---

## 📝 Example Commands

- *"Find doc1wire.pdf and send it to laasya2279@gmail.com"*
- *"Search for my resume and email it to my friend"* (Jarvis will ask for the friend's email or resolve it from `contacts.json`)
- *"Open chrome and go to google.com"*

---

## ⚠️ Troubleshooting

- **Proxy Errors**: If the UI says "ECONNREFUSED", ensure the Uvicorn backend is running on port 8000.
- **Attachment Fails**: Ensure the file exists in your Downloads or specified folder. ARC will log the exact path it's trying to attach.
- **Window Doesn't Close**: Ensure you are not manually clicking the Gmail window while ARC is trying to send; this can interrupt the `Ctrl+Enter` shortcut.
