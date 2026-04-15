"""
Text Normalizer — cleans raw Whisper output before intent matching.

Pipeline:  raw text → lowercase → strip fillers → fix corrections
           → normalize synonyms → clean whitespace → NormalizedCommand

Runs in <1ms. No ML model needed.
"""

import re
from dataclasses import dataclass, field


@dataclass
class NormalizedCommand:
    """Result of normalizing a raw Whisper transcript."""
    raw:     str              # Original whisper output
    cleaned: str              # Cleaned, normalized command
    tokens:  list = field(default_factory=list)  # Individual word tokens


# ─── Filler Words ────────────────────────────────────────────
# Stripped entirely — these add no intent information.
FILLER_WORDS = {
    "um", "uh", "uhh", "umm", "hmm", "hmmm",
    "like", "basically", "literally", "actually",
    "please", "kindly", "can you", "could you",
    "would you", "will you", "hey", "yo", "okay",
    "so", "well", "just", "right", "alright",
    "i want you to", "i need you to", "i want to",
    "go ahead and", "i'd like you to", "i'd like to",
}

# Multi-word fillers — matched as phrases before word-level removal
FILLER_PHRASES = [
    "hey jarvis", "jarvis", "hey there", "excuse me",
    "can you please", "could you please", "would you please",
    "would you kindly", "if you could", "if you can",
    "i want you to", "i need you to", "go ahead and",
    "i'd like you to", "i'd like to", "i want to",
    "for me please", "for me", "real quick", "right now",
    "as soon as possible", "when you get a chance",
    "do me a favor and", "be a dear and",
]

# ─── Whisper Mistranscription Corrections ────────────────────
# Expanded from the original CORRECTIONS in speech_to_text.py
CORRECTIONS = {
    # Jarvis mishears
    "jihadis":    "jarvis",
    "javas":      "jarvis",
    "davas":      "jarvis",
    "java":       "jarvis",
    "jabas":      "jarvis",
    "dava":       "jarvis",
    "travis":     "jarvis",
    "jervis":     "jarvis",
    "jarves":     "jarvis",
    "javis":      "jarvis",
    # App names
    "crome":      "chrome",
    "chrom":      "chrome",
    "saf":        "safari",
    "safarie":    "safari",
    "vs code":    "vscode",
    "v s code":   "vscode",
    "visual studio code": "vscode",
    "v.s. code":  "vscode",
    # Common mishears
    "screeshot":  "screenshot",
    "screen shot":"screenshot",
    "volum":      "volume",
    "brightnes":  "brightness",
    "minimise":   "minimize",
    "minimze":    "minimize",
    "maximise":   "maximize",
    "maximze":    "maximize",
    "ful screen": "fullscreen",
    "full screen":"fullscreen",
    "shut down":  "shutdown",
    "re start":   "restart",
    "e mail":     "email",
    "g mail":     "gmail",
}

# ─── Synonym Normalization ──────────────────────────────────
# Maps user vocabulary to canonical terms used by the intent engine.
# IMPORTANT: These are matched as WHOLE WORDS (regex \b boundaries)
# to avoid corrupting words like "inside" → "insvscode" from "ide".
SYNONYMS = {
    # Apps
    "editor":           "vscode",
    "code editor":      "vscode",
    "coding editor":    "vscode",
    "my editor":        "vscode",
    "ide":              "vscode",
    "browser":          "safari",
    "web browser":      "safari",
    "internet":         "safari",
    "the web":          "safari",
    "command line":     "terminal",
    "shell":            "terminal",
    "console":          "terminal",
    # System
    "my laptop":        "mac",
    "my computer":      "mac",
    "the computer":     "mac",
    "this machine":     "mac",
    "the system":       "mac",
    "pc":               "mac",
    # Folders
    "download folder":  "downloads",
    "my downloads":     "downloads",
    "desktop folder":   "desktop",
    "my desktop":       "desktop",
    "documents folder": "documents",
    "my documents":     "documents",
    "my files":         "documents",
    # Actions
    "turn off":         "shutdown",
    "power off":        "shutdown",
    "switch off":       "shutdown",
    "reboot":           "restart",
    "put to sleep":     "sleep",
    "nap mode":         "sleep",
    "silence":          "mute",
    "quiet":            "mute",
    "shut up":          "mute",
    "louder":           "volume up",
    "quieter":          "volume down",
    "turn up":          "volume up",
    "turn down":        "volume down",
    "brighter":         "brightness up",
    "dimmer":           "brightness down",
    "capture screen":   "screenshot",
    "take a snap":      "screenshot",
    "screen capture":   "screenshot",
    "inbox":            "emails",
    "mail":             "emails",
    "my mail":          "emails",
}


def _word_boundary_replace(text: str, old: str, new: str) -> str:
    """Replace `old` with `new` only when `old` appears as a whole word/phrase."""
    pattern = r'\b' + re.escape(old) + r'\b'
    return re.sub(pattern, new, text)


def normalize(raw_text: str) -> NormalizedCommand:
    """
    Full normalization pipeline.
    Returns NormalizedCommand with raw, cleaned, and tokens.
    """
    if not raw_text:
        return NormalizedCommand(raw="", cleaned="", tokens=[])

    text = raw_text.strip().lower()
    original = text

    # Step 1: Apply Whisper corrections (word-boundary safe)
    for wrong, right in sorted(CORRECTIONS.items(), key=lambda x: len(x[0]), reverse=True):
        text = _word_boundary_replace(text, wrong, right)

    # Step 1.5: Convert "dot" to "." for file extensions
    # e.g. "resume dot pdf" → "resume.pdf", "notes dot txt" → "notes.txt"
    text = re.sub(r'(\w+)\s+dot\s+(\w+)', r'\1.\2', text)

    # Step 2: Remove filler phrases (multi-word, order matters)
    for phrase in sorted(FILLER_PHRASES, key=len, reverse=True):
        text = text.replace(phrase, " ")

    # Step 3: Remove single filler words
    words = text.split()
    words = [w for w in words if w not in FILLER_WORDS]
    text = " ".join(words)

    # Step 4: Normalize synonyms (word-boundary safe, longest-first)
    for synonym, canonical in sorted(SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True):
        text = _word_boundary_replace(text, synonym, canonical)

    # Step 5: Clean up whitespace and punctuation
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[.,!?;:]+$', '', text).strip()

    tokens = text.split() if text else []

    return NormalizedCommand(
        raw=original,
        cleaned=text,
        tokens=tokens
    )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "hey jarvis can you please open my coding editor",
        "umm like open the browser for me please",
        "uh could you turn up the volume by 30",
        "yo shut down my laptop",
        "jarvis search for python tutorials on the web",
        "hey can you take a screenshot real quick",
        "uh read my inbox",
        "could you please open the download folder for me",
        "like close it",
        "um basically open vscode and then like open safari",
    ]

    print("=" * 60)
    print("  TEXT NORMALIZER TEST")
    print("=" * 60)

    for raw in tests:
        result = normalize(raw)
        print(f"\n  Raw:     '{result.raw}'")
        print(f"  Cleaned: '{result.cleaned}'")
        print(f"  Tokens:  {result.tokens}")
        print("-" * 60)
