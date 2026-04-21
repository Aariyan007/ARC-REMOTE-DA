"""
Fast Intent Engine — embedding-based intent classification.

Replaces the static INSTANT_CACHE with a semantic similarity engine.
Uses sentence-transformers (all-MiniLM-L6-v2) for embeddings.
Runs in ~5-15ms on CPU. No LLM call needed.

Pipeline:
    normalized_text → embed → cosine_similarity(all_intents) → best_match
"""

import os
import sys
import json
import warnings
import numpy as np
from typing import Optional
from dataclasses import dataclass

# Suppress torchcodec FFmpeg errors (not needed for embeddings)
os.environ.setdefault("TORCHCODEC_DISABLE_LOAD", "1")
warnings.filterwarnings("ignore", message=".*torchcodec.*")
warnings.filterwarnings("ignore", message=".*FFmpeg.*")

# Lazy load to avoid slow import at startup
_model = None
_cross_encoder = None             # Cross-encoder for precision reranking
_intent_embeddings = None   # { action: np.array of shape (N, dim) }
_intent_examples   = None   # { action: [example1, example2, ...] }


@dataclass
class IntentResult:
    """Result from the fast intent engine."""
    action:     str              # Resolved action name
    confidence: float            # 0.0 - 1.0 cosine similarity
    source:     str              # "builtin" | "learned" | "none"
    matched_example: str = ""    # Which example it matched against


# ─── Built-in Intent Registry ───────────────────────────────
# These are the seed examples for each action.
# The more examples, the better the matching accuracy.
INTENT_REGISTRY = {
    # ── Apps ─────────────────────────────────────────────────
    "open_app": [
        "open vscode", "launch vscode", "start vscode", "fire up vscode",
        "open safari", "launch safari", "start safari", "open browser",
        "open terminal", "launch terminal", "start terminal", "open shell",
        "open chrome", "launch chrome", "start chrome",
        "open finder", "launch finder",
        "open notes", "open music", "open spotify",
        "open slack", "open discord", "open zoom",
        "open an app", "launch an application",
    ],
    "close_app": [
        "close vscode", "quit vscode", "exit vscode",
        "close safari", "quit safari", "exit safari",
        "close terminal", "quit terminal", "exit terminal",
        "close chrome", "quit chrome",
        "close the app", "quit the application", "kill the app",
    ],
    "switch_to_app": [
        "switch to vscode", "go to vscode", "bring up vscode",
        "switch to safari", "go to safari", "bring up safari",
        "switch to terminal", "go to terminal",
        "switch to chrome", "go to chrome",
        "switch app", "go to an app", "bring up another app",
    ],

    # ── Volume ───────────────────────────────────────────────
    "volume_up": [
        "volume up", "turn up the volume", "increase volume",
        "make it louder", "louder", "crank it up",
        "volume up by 20", "raise the volume",
    ],
    "volume_down": [
        "volume down", "turn down the volume", "decrease volume",
        "make it quieter", "quieter", "lower the volume",
        "volume down by 20", "reduce volume",
    ],
    "mute": [
        "mute", "mute the sound", "silence", "mute audio",
        "turn off sound", "mute everything",
    ],
    "unmute": [
        "unmute", "unmute the sound", "turn on sound",
        "enable audio", "unmute audio",
    ],
    "get_volume": [
        "what's the volume", "current volume", "volume level",
        "how loud is it", "get volume",
    ],

    # ── Brightness ────────────────────────────────────────────
    "brightness_up": [
        "brightness up", "increase brightness", "brighter",
        "make it brighter", "screen brighter", "more brightness",
    ],
    "brightness_down": [
        "brightness down", "decrease brightness", "dimmer",
        "make it dimmer", "screen dimmer", "less brightness",
    ],

    # ── System ───────────────────────────────────────────────
    "lock_screen": [
        "lock screen", "lock the screen", "lock my screen",
        "lock my mac", "lock computer",
    ],
    "shutdown_pc": [
        "shutdown", "shut down", "turn off", "power off",
        "shutdown my mac", "turn off computer",
    ],
    "restart_pc": [
        "restart", "reboot", "restart my mac",
        "restart computer", "reboot system",
    ],
    "sleep_mac": [
        "sleep", "sleep mode", "put to sleep",
        "sleep my mac", "nap mode", "go to sleep",
    ],
    "take_screenshot": [
        "take screenshot", "screenshot", "capture screen",
        "screen capture", "take a snap", "snapshot",
        "what is on my screen", "what's on my screen",
        "tell me what's on my screen", "what am i seeing",
        "what am i looking at", "describe my screen",
        "what is there on my screen", "show me what's on screen",
        "what do you see on my screen", "what can you see on screen",
        "can you tell me what's on my screen",
        "what is on the screen right now",
        "what am i seeing on my screen right now",
    ],
    "get_battery": [
        "battery", "battery level", "how much battery",
        "check battery", "battery percentage", "power level",
    ],

    # ── Time & Date ──────────────────────────────────────────
    "tell_time": [
        "what time is it", "current time", "what's the time",
        "time please", "tell me the time", "what time",
    ],
    "tell_date": [
        "what's the date", "what is the date", "today's date",
        "current date", "tell me the date", "what day is it",
    ],

    # ── Weather ──────────────────────────────────────────────
    "tell_weather": [
        "weather", "what's the weather", "how's the weather",
        "temperature", "is it hot", "is it cold",
        "weather outside", "what's it like outside",
    ],

    # ── Web Search ───────────────────────────────────────────
    "search_google": [
        "search google", "google search", "search for",
        "look up", "search the web", "google",
        "search online", "browse for", "find online",
    ],

    # ── Playwright browser (DOM-first; distinct from OS new_tab) ─
    "open_url": [
        "open https://", "go to https://", "visit https://",
        "navigate to https://", "open http://",
        "go to github.com", "visit reddit.com", "open example.com",
        "navigate to news.ycombinator.com", "browse to stackoverflow.com",
    ],
    "web_back": [
        "browser go back", "web page back", "go back in the browser",
        "previous web page", "browser back button",
    ],
    "web_refresh": [
        "reload web page", "refresh this webpage", "reload the browser page",
        "refresh browser page", "reload the site",
    ],
    "web_new_tab": [
        "jarvis new browser tab", "automation browser new tab",
        "controlled browser new tab", "new tab in the automation browser",
    ],
    "web_close_tab": [
        "close automation browser tab", "close jarvis browser tab",
        "close the automation tab", "close controlled browser tab",
    ],

    # ── Folders ──────────────────────────────────────────────
    "open_folder": [
        "open downloads", "open desktop", "open documents",
        "open folder", "open my files", "show folder",
        "go to downloads", "go to desktop",
    ],
    "create_folder": [
        "create folder", "make folder", "new folder",
        "create a directory", "make a new folder",
    ],
    "search_file": [
        "search file", "find file", "look for file",
        "where is my file", "locate file", "find my",
    ],

    # ── Email ────────────────────────────────────────────────
    "read_emails": [
        "read my emails", "check my emails", "check inbox",
        "any new emails", "read emails", "show my emails",
        "check my inbox", "any emails",
    ],
    "search_emails": [
        "search emails", "find emails", "emails from",
        "any emails about", "search my inbox",
    ],
    "send_email": [
        "send email", "compose email", "write email",
        "email to", "send a message", "compose mail",
    ],
    "open_gmail": [
        "open gmail", "open my email", "open mail",
        "go to gmail", "launch gmail",
    ],

    # ── Window Management ────────────────────────────────────
    "minimise_all": [
        "minimize all", "minimize everything", "hide all windows",
        "minimize all windows", "clear windows",
    ],
    "show_desktop": [
        "show desktop", "go to desktop", "reveal desktop",
        "clear desktop", "desktop",
    ],
    "close_window": [
        "close window", "close this window", "shut window",
    ],
    "close_tab": [
        "close tab", "close this tab", "shut tab",
    ],
    "new_tab": [
        "new tab", "open new tab", "open tab",
    ],
    "fullscreen": [
        "fullscreen", "full screen", "make it fullscreen",
        "maximize", "go fullscreen",
    ],
    "mission_control": [
        "mission control", "show all windows",
        "expose", "all windows", "overview",
    ],
    "minimise_app": [
        "minimize safari", "minimize vscode", "minimize terminal",
        "hide safari", "hide vscode", "hide app",
        "minimize an app", "minimize this app",
    ],

    # ── Routines ─────────────────────────────────────────────
    "start_work_day": [
        "start my day", "work mode", "begin work",
        "start work", "work time", "let's work",
    ],
    "end_work_day": [
        "end my day", "finish work", "wrap up",
        "end work", "done working", "stop working",
    ],
    "morning_briefing": [
        "morning briefing", "brief me", "what's today like",
        "give me a briefing", "daily brief", "what's happening today",
    ],
    "read_news": [
        "what's the news", "read me the news", "today's news",
        "news headlines", "what's in the news today",
        "tell me the news", "world news", "any news today",
        "what is today's news man",
    ],

    # ── PDF ───────────────────────────────────────────────────
    "summarise_pdf": [
        "summarize pdf", "summarise pdf", "read pdf",
        "read this pdf", "what does this pdf say",
        "pdf summary", "analyze pdf",
    ],

    # ── General Knowledge / Questions ────────────────────────
    "answer_question": [
        "what is", "who is", "what are", "how does",
        "explain", "tell me about", "what does",
        "how many", "when was", "where is",
        "why is", "why does", "can you explain",
        "what happened", "what's the difference between",
        "how do i", "how to", "what should i",
        "define", "describe", "meaning of",
        "what is machine learning", "who made you",
        "what is python", "tell me about india",
        "explain quantum computing", "who is elon musk",
        "what is ai", "how does blockchain work",
        "what's the capital of france", "who invented the internet",
        "what is the meaning of life", "how far is the moon",
        "what is the population of india",
        "tell me all the details about", "give me all details about",
        "tell me everything about", "give me details regarding",
        "what do you know about", "find out about",
        "what all do you know about", "research about",
        "what is the website", "find out what is",
        "let me know all about", "tell me all about",
        "details about", "details regarding",
    ],

    # ── Casual Chat / Greetings ──────────────────────────────
    "general_chat": [
        "how are you", "what's up", "hey jarvis",
        "hello", "hi there", "good morning jarvis",
        "good night", "thanks jarvis", "thank you",
        "you're awesome", "nice job", "well done",
        "what are you doing", "are you there",
        "miss you", "love you", "you're funny",
        "tell me a joke", "say something funny",
        "i'm bored", "entertain me", "what's new",
        "how do you feel", "are you real",
        "what can you do", "help me", "i need help",
        "good evening", "good afternoon",
        "you're smart", "you're the best",
        "what have we talked about", "what all conversations did we have",
        "what did we discuss", "our previous conversations",
        "what were we talking about", "recall our conversation",
        "how are we doing", "how are you feeling",
        "let's do something", "i'm bored let's do something",
    ],

    # ── File Operations ──────────────────────────────────────
    "read_file": [
        "read file", "read notes", "open and read",
        "what's in this file", "show file contents",
        "read notes.txt", "read the file",
        "read my notes.txt", "what's in notes.txt",
        "read that file", "open and read the file",
        "read my notes", "show me the file",
        "read the contents", "read the contents of this file",
        "read the contents in the file", "show me the contents",
        "what are the contents", "read contents of resume",
        "read the contents in superman", "read file contents",
        "read resume.pdf", "read the resume file",
        "what does the file say", "open and read resume",
        "read that document", "read the particular file",
        "show what's in the file", "read me that file",
    ],
    "create_file": [
        "create file", "make file", "new file",
        "create a file called", "make a new file",
        "create a file called ideas", "make a file named test",
        "create superman file", "create a file called superman",
        "make a new file called notes", "create notes file",
        "new file called ideas", "create a text file",
        "create a document called superman", "make a document",
        "create a pdf", "make a word document",
        "create a file in document format", "new document file",
        "create a python file", "make a markdown file",
        "create a file named superman.docx",
        "make a spreadsheet", "create a csv file",
        "create an html file", "make a json file",
        "create a python script called test",
        "make me a word file", "new word document",
        "create a presentation", "make a pages document",
        "new spreadsheet called budget",
        "create a yaml file", "make a log file",
    ],
    "edit_file": [
        "edit file", "add text to the file", "write inside the file",
        "add contents to the file", "put some text in", "add something like",
        "write this down inside", "edit notes dot txt", "add something to superman",
        "write something in the file", "add text to that file",
        "write in the file", "add some content",
        "put text in create.txt", "write hi in the file",
        "add contents to the file", "write in create.txt",
        "write contents in it", "add hi i am superman to the file",
        "add some content to that file", "put this in the file",
        "write to the file", "add text in it",
        "write particular things in that file",
        "i want to write in the file", "add contents in it",
        "write some text inside the file", "add text to the document",
        "write in that particular file", "add the contents",
        "write hello world in it", "add this text to the file",
        "type something in it", "insert text into the file",
    ],
    "create_and_edit_file": [
        "create a file and write something in it",
        "make a file called notes and add hello world",
        "create test.txt and write hi there inside",
        "make a file named ideas then add some text",
        "create a document and put my notes in it",
        "create superman.txt and write i am superman",
        "make a new file and add contents",
        "create a file called resume and write my name",
    ],
    "delete_file": [
        "delete file", "remove file", "trash file",
        "delete this file", "remove that file",
        "get rid of that file", "trash that file",
        "delete notes.txt", "remove superman.txt",
        "move that file to trash", "delete it",
    ],
    "rename_file": [
        "rename file", "rename this", "change name",
        "rename to", "rename file to",
        "rename notes.txt to ideas.txt",
        "change the file name", "rename this to something else",
        "rename that file", "change the name of that file",
    ],
    "copy_file": [
        "copy file", "copy this file", "duplicate file",
        "copy to desktop", "copy to downloads",
        "copy that file", "make a copy",
        "duplicate that file", "copy it to desktop",
    ],
    "get_recent_files": [
        "recent files", "what files did i work on",
        "what did i edit today", "show recent files",
        "my recent files", "lately edited files",
        "what files did i work on today",
        "show me my recent files", "what have i been working on",
        "recent documents", "recently modified files",
    ],

    # ── Music / Spotify ─────────────────────────────────────
    "play_song": [
        "play a song", "play some music", "play music for me",
        "play a song on spotify", "play music on spotify",
        "play despacito", "play shape of you", "can you play a song",
        "play something", "put on some music", "play my music",
        "play the song", "play that song", "play this song",
        "play music from spotify", "play the music from spotify",
        "could you play music", "play music please",
        "play a track", "put on a song", "i want to hear music",
        "play blinding lights", "play bohemian rhapsody",
    ],
    "play_mood_music": [
        "play music according to my mood", "play something for my mood",
        "play music based on how i feel", "mood music", "play chill music",
        "play something relaxing", "play happy music", "play sad music",
        "play focus music", "play workout music", "play party music",
        "play something based on my mood", "match my mood with music",
        "play upbeat music", "play calm music", "play energetic music",
        "play something to help me focus", "play study music",
        "play lo-fi", "play lo-fi beats",
    ],
    # ── Memory / Knowledge Base (Second Brain) ───────────────
    "save_note": [
        "save note", "create a note", "remember this",
        "save a new note", "put this in my brain",
        "write a note", "make a note", "save this to my brain",
        "create a new memory", "store this",
        "save to obsidian", "create a new note in obsidian",
        "take a note", "write this down",
        "save note that my favorite fruit is apple",
        "remember that my name is alex",
        "create a note saying that i need milk",
        "save this memory to the brain",
    ],
    "append_note": [
        "append note", "add to note", "update note",
        "add this to my daily note", "append to daily note",
        "add this to the project note", "update my notes",
        "write this into my note", "add some info to the note",
        "append that the meeting is cancelled",
        "add to the daily note that i finished the work",
    ],
    "search_vault": [
        "search my brain", "search vault", "search obsidian",
        "do i have any notes on", "find in my notes",
        "search my knowledge base", "look up in my brain",
        "check my notes for", "what do my notes say about",
    ],

    # ── Window Management ────────────────────────────────────
    "move_window": [
        "move this to the left", "move this to the right",
        "move vscode to the left", "move chrome to the right",
        "snap this window to the right", "snap to the left",
        "put this on the left half", "this app to the left",
        "move this app to the right side", "put this on the right",
        "move this window left", "move this window right",
        "move this to the center", "center this window",
        "tile this to the left", "tile this to the right",
    ],
    "resize_window": [
        "resize this to 50%", "make this half the screen",
        "this app by 50%", "make this window smaller",
        "resize to fullscreen", "make it take half the screen",
        "make this window bigger", "resize this app",
        "make this 75%", "make this quarter of the screen",
        "resize this window to half", "make this take up the whole screen",
    ],
    "tile_windows": [
        "tile vscode and chrome", "put these side by side",
        "tile these windows", "split screen with",
        "side by side layout", "tile two windows",
    ],
}

# ─── Negative Examples (anti-match patterns) ────────────────
# These penalize specific (action, text) pairs during reranking
NEGATIVE_EXAMPLES = {
    "brightness_up": [
        "what is on my screen", "what's on my screen",
        "tell me what's on my screen", "what am i seeing",
        "what am i looking at", "describe my screen",
    ],
    "brightness_down": [
        "what is on my screen", "what's on my screen",
        "what am i seeing on my screen",
    ],
    "open_app": [
        "tell me about", "tell me all the details about",
        "what do you know about", "tell me everything about",
        "give me details about", "research about",
        "what is the website", "find out about",
    ],
    "morning_briefing": [
        "what all conversations did we have",
        "what did we discuss", "what were we talking about",
    ],
    "switch_to_app": [
        "move this to the left", "move this to the right",
        "resize this", "this app by 50%",
        "make this half the screen",
    ],
}



def _get_cross_encoder():
    """Lazy-load the cross-encoder model for reranking."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            print("Loading cross-encoder for reranking...")
            _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            print("Cross-encoder ready")
        except Exception as e:
            print(f"Warning: Cross-encoder not available: {e}")
            _cross_encoder = False  # Sentinel: tried but failed
    return _cross_encoder if _cross_encoder is not False else None


def _get_model():
    """
    Lazy-load the sentence transformer model.

    Resolution order:
      1. SENTENCE_TRANSFORMERS_HOME env var → local directory (fully offline)
      2. Default HuggingFace cache (~/.cache/huggingface/hub) if already cached
      3. Network download as last resort

    Raises RuntimeError with a clear message if the model cannot be loaded,
    so callers can degrade gracefully instead of stalling.
    """
    global _model
    if _model is None:
        import os
        from sentence_transformers import SentenceTransformer

        MODEL_NAME = "all-MiniLM-L6-v2"

        # 1. Check for an explicit local path override
        local_path = os.environ.get("SENTENCE_TRANSFORMERS_HOME", "")
        if local_path:
            candidate = os.path.join(local_path, MODEL_NAME)
            if os.path.isdir(candidate):
                print(f"Loading sentence-transformer from local path: {candidate}")
                try:
                    _model = SentenceTransformer(candidate)
                    print("Model loaded (offline).")
                    return _model
                except Exception as e:
                    print(f"Warning: local model load failed ({e}), trying cache...")

        # 2. Check default HuggingFace cache (no network call if already cached)
        cache_dir = os.path.expanduser(
            os.environ.get("HF_HOME",
                os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))
        )
        # HF hub stores models as "models--org--name"
        hf_cache_name = f"models--sentence-transformers--{MODEL_NAME}"
        if os.path.isdir(os.path.join(cache_dir, hf_cache_name)):
            print(f"Loading sentence-transformer from HuggingFace cache...")
            try:
                _model = SentenceTransformer(MODEL_NAME, cache_folder=cache_dir)
                print("Model loaded (cached).")
                return _model
            except Exception as e:
                print(f"Warning: cached model load failed ({e}), attempting download...")

        # 3. Network download — last resort
        print(f"Downloading sentence-transformer model '{MODEL_NAME}' (first-time setup)...")
        print("Tip: set SENTENCE_TRANSFORMERS_HOME to a local dir to avoid this.")
        try:
            _model = SentenceTransformer(MODEL_NAME)
            print("Model loaded (downloaded).")
        except Exception as e:
            raise RuntimeError(
                f"Could not load sentence-transformer model '{MODEL_NAME}'.\n"
                f"Reason: {e}\n"
                f"Fix: run `pip install sentence-transformers` and ensure network "
                f"access on first run, or set SENTENCE_TRANSFORMERS_HOME to a "
                f"directory containing a pre-downloaded '{MODEL_NAME}' folder."
            ) from e
    return _model


def _load_intent_patches() -> dict:
    """
    Load auto-generated intent patches from retrospective learning.
    Returns { action: [example1, ...] } for merging into registry.
    """
    patches_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'intent_patches.json'
    )
    if not os.path.exists(patches_path):
        return {}

    try:
        with open(patches_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        patch_examples = {}
        for patch in data.get("patches", []):
            action = patch.get("action", "")
            examples = patch.get("add_examples", [])
            if action and examples:
                if action not in patch_examples:
                    patch_examples[action] = []
                patch_examples[action].extend(examples)

        if patch_examples:
            total = sum(len(e) for e in patch_examples.values())
            print(f"[R] Loaded {total} retrospective patches across "
                  f"{len(patch_examples)} intents")

        return patch_examples
    except Exception as e:
        print(f"Warning: Could not load intent patches: {e}")
        return {}


def _build_embeddings(extra_examples: dict = None):
    """
    Pre-compute embeddings for all intent examples.
    Called once on startup and when learned intents change.

    Merge order: built-in registry -> retrospective patches -> learned intents
    """
    global _intent_embeddings, _intent_examples

    model = _get_model()

    # Merge built-in + patches + learned examples
    all_examples = {}
    for action, examples in INTENT_REGISTRY.items():
        all_examples[action] = list(examples)  # copy

    # Auto-load retrospective patches
    patches = _load_intent_patches()
    for action, patched in patches.items():
        if action in all_examples:
            existing = set(all_examples[action])
            all_examples[action].extend(
                [e for e in patched if e not in existing]
            )
        else:
            all_examples[action] = patched

    # Learned intents from Gemini fallback
    if extra_examples:
        for action, learned in extra_examples.items():
            if action in all_examples:
                existing = set(all_examples[action])
                all_examples[action].extend(
                    [e for e in learned if e not in existing]
                )
            else:
                all_examples[action] = learned

    # Compute embeddings
    _intent_examples   = {}
    _intent_embeddings = {}

    for action, examples in all_examples.items():
        _intent_examples[action]   = examples
        embeddings = model.encode(examples, convert_to_numpy=True, normalize_embeddings=True)
        _intent_embeddings[action] = embeddings

    total = sum(len(e) for e in _intent_examples.values())
    print(f"📊 Indexed {total} examples across {len(_intent_examples)} intents")


def initialize(learned_examples: dict = None):
    """
    Initialize the fast intent engine.
    Should be called once on startup.

    Args:
        learned_examples: { action: [example1, ...] } from learned_intents DB
    """
    _build_embeddings(learned_examples)


def reload_learned(learned_examples: dict):
    """Reload with new learned examples (after a Gemini resolution)."""
    _build_embeddings(learned_examples)


def classify(text: str) -> IntentResult:
    """
    Classify a normalized command text into an intent.

    Pipeline:
        1. Bi-encoder: cosine similarity → Top-5 candidates (fast)
        2. Cross-encoder: rerank Top-5 for precision (accurate)

    Args:
        text: Normalized command text

    Returns:
        IntentResult with action, confidence, source, and matched_example
    """
    if not text or not text.strip():
        return IntentResult(action="", confidence=0.0, source="none")

    if _intent_embeddings is None:
        initialize()

    model = _get_model()

    # ── Step 1: Bi-encoder fast retrieval (Top-5) ────────────
    input_embedding = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]

    # Collect ALL candidates with scores
    all_candidates = []  # [(action, score, example, source), ...]

    for action, embeddings in _intent_embeddings.items():
        similarities = np.dot(embeddings, input_embedding)
        max_idx      = int(np.argmax(similarities))
        max_sim      = float(similarities[max_idx])

        builtin_count = len(INTENT_REGISTRY.get(action, []))
        source = "learned" if max_idx >= builtin_count else "builtin"
        example = _intent_examples[action][max_idx]

        all_candidates.append((action, max_sim, example, source))

    # Sort by score descending, take Top-5
    all_candidates.sort(key=lambda x: x[1], reverse=True)
    top5 = all_candidates[:5]

    if not top5:
        return IntentResult(action="", confidence=0.0, source="none")

    # ── Step 2: Cross-encoder reranking ──────────────────────
    cross_enc = _get_cross_encoder()

    if cross_enc and len(top5) > 1:
        # Build (input, example) pairs for cross-encoder
        pairs = [(text, c[2]) for c in top5]

        try:
            scores = cross_enc.predict(pairs)

            # Apply negative example penalties
            for i, (action, _, example, _) in enumerate(top5):
                neg_list = NEGATIVE_EXAMPLES.get(action, [])
                for neg in neg_list:
                    if neg.lower() in text.lower() or text.lower() in neg.lower():
                        scores[i] -= 2.0  # Heavy penalty
                        break

            best_idx = int(np.argmax(scores))
            best = top5[best_idx]

            # Normalize cross-encoder score to 0-1 range
            # ms-marco scores are typically -10 to +10
            raw_score = float(scores[best_idx])
            norm_conf = 1.0 / (1.0 + np.exp(-raw_score))  # sigmoid

            return IntentResult(
                action=best[0],
                confidence=norm_conf,
                source=best[3],
                matched_example=best[2],
            )
        except Exception as e:
            print(f"Warning: Cross-encoder rerank failed: {e}")
            # Fall through to bi-encoder result

    # ── Fallback: use bi-encoder top result ───────────────────
    best = top5[0]
    return IntentResult(
        action=best[0],
        confidence=best[1],
        source=best[3],
        matched_example=best[2],
    )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  FAST INTENT ENGINE TEST")
    print("=" * 60)

    # Initialize
    initialize()

    # Test commands
    tests = [
        "open vscode",
        "launch my editor",
        "fire up the browser",
        "crank up the volume",
        "what time is it bro",
        "check my inbox",
        "search for python tutorials",
        "take a screenshot",
        "put my mac to sleep",
        "show all windows",
        "read my recent files",
        "create file called notes",
        "how much battery do i have",
        "open downloads folder",
        "send an email",
        "close everything",            # should be lower confidence
        "make me a sandwich",          # should be very low confidence
    ]

    print(f"\n{'Command':<40} {'Action':<20} {'Conf':>6} {'Source':<10} {'Matched'}")
    print("-" * 110)

    for cmd in tests:
        result = classify(cmd)
        print(f"  {cmd:<38} {result.action:<20} {result.confidence:>5.2f}  {result.source:<10} {result.matched_example}")
