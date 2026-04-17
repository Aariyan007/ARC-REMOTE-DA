"""
Continuous Memory — Structured long-term memory for user-specific information.

Implements the JARVIS memory protocol:
    - 3-level extraction (Explicit / Strong Signal / Weak → ignore)
    - Typed entries: preference, person, habit, context, fact
    - Memory decay: confidence degrades over time without access
    - Conflict resolution: new > old confidence → replace
    - Reinforcement: successful usage boosts confidence
    - User control: view, delete, clear

Storage: data/continuous_memory.json
Bridge: Also indexes into VectorMemory for semantic recall.

Cross-platform: Pure Python, JSON persistence.
"""

import os
import re
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List
from dataclasses import dataclass, field, asdict


# ─── Settings ────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.dirname(__file__))
MEMORY_PATH     = os.path.join(BASE_DIR, "data", "continuous_memory.json")
MAX_MEMORIES    = 500
DEFAULT_DECAY   = 0.995      # Per-day decay rate
MIN_CONFIDENCE  = 0.15       # Below this → auto-prune
REINFORCE_BOOST = 0.05       # Boost on successful usage
REINFORCE_CAP   = 1.0        # Max confidence after boost
# ─────────────────────────────────────────────────────────────


# ─── Extraction Confidence Thresholds ────────────────────────
EXPLICIT_THRESHOLD      = 0.8   # "Remember this", "I prefer" → ALWAYS store
STRONG_SIGNAL_THRESHOLD = 0.6   # "I always use VSCode" → store medium conf
# Below 0.6 → IGNORE (weak signal)
# ─────────────────────────────────────────────────────────────


# ─── Extraction Patterns ────────────────────────────────────
# Level 1: Explicit (confidence ≥ 0.8)
EXPLICIT_PATTERNS = [
    r"\bremember\s+(?:that|this)\b",
    r"\bI\s+prefer\b",
    r"\bmy\s+(?:favorite|favourite)\b",
    r"\balways\s+use\b",
    r"\bnever\s+use\b",
    r"\bI\s+(?:like|love|hate|dislike)\b",
    r"\bset\s+(?:my|the)\s+default\b",
    r"\bdon'?t\s+(?:ever|ever\s+)use\b",
    r"\bkeep\s+(?:using|this)\b",
]

# Level 2: Strong signal (confidence 0.6–0.8)
STRONG_SIGNAL_PATTERNS = [
    r"\bI\s+(?:usually|typically|normally)\s+use\b",
    r"\bI\s+(?:work|code)\s+(?:in|with)\b",
    r"\bmy\s+(?:name|editor|browser|tool)\s+is\b",
    r"\bI'?m\s+(?:a|an)\s+\w+\s+(?:developer|designer|student|engineer)\b",
    r"\bI\s+(?:go\s+by|am\s+called)\b",
]

# ─── Sensitive Data Filters (NEVER store) ────────────────────
SENSITIVE_PATTERNS = [
    r"\bpassword\b", r"\bsecret\b", r"\bapi[_\s]?key\b",
    r"\btoken\b", r"\bcredit\s*card\b", r"\bssn\b",
    r"\bsocial\s+security\b", r"\bbank\s+account\b",
    r"\bpin\s+(?:number|code)\b",
]


# ─── Memory Entry ───────────────────────────────────────────
@dataclass
class MemoryEntry:
    """A single structured memory."""
    id:            str
    type:          str              # preference | person | habit | context | fact
    key:           str              # e.g., "editor", "name", "morning_routine"
    value:         str              # e.g., "VSCode", "Aariyan", "open terminal"
    confidence:    float = 0.8
    timestamp:     str   = ""
    source:        str   = "explicit"    # explicit | strong_signal | inferred
    access_count:  int   = 0
    last_accessed: str   = ""
    decay_rate:    float = DEFAULT_DECAY

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.last_accessed:
            self.last_accessed = self.timestamp

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "MemoryEntry":
        return MemoryEntry(**{k: v for k, v in d.items()
                             if k in MemoryEntry.__dataclass_fields__})

    def decayed_confidence(self) -> float:
        """Calculate confidence after time-based decay."""
        try:
            last = datetime.fromisoformat(self.last_accessed)
            days_elapsed = (datetime.now() - last).total_seconds() / 86400
            return self.confidence * (self.decay_rate ** days_elapsed)
        except Exception:
            return self.confidence


# ─── Continuous Memory Store ────────────────────────────────
class ContinuousMemory:
    """
    Structured long-term memory with 3-level extraction,
    decay, conflict resolution, and user control.

    Usage:
        mem = ContinuousMemory()
        mem.store("preference", "editor", "VSCode", confidence=0.9)
        prefs = mem.get_preferences()
        mem.reinforce("editor")
    """

    def __init__(self):
        self._entries: list[MemoryEntry] = []
        self._lock = threading.Lock()
        self._load()

    # ─── Core CRUD ───────────────────────────────────────────

    def store(
        self,
        mem_type:   str,
        key:        str,
        value:      str,
        confidence: float = 0.8,
        source:     str   = "explicit",
    ) -> Optional[str]:
        """
        Store or update a memory entry.

        Conflict resolution:
            If key exists with same type:
                - new confidence > old → replace
                - new confidence ≤ old → merge (update access time)

        Returns entry ID or None if filtered.
        """
        # Safety: block sensitive data
        if self._is_sensitive(f"{key} {value}"):
            print(f"🛡️  Memory blocked: sensitive data detected for key='{key}'")
            return None

        with self._lock:
            # Check for existing entry with same type+key
            existing = self._find(mem_type, key)

            if existing:
                if confidence > existing.confidence:
                    # Conflict resolution: new wins
                    existing.value = value
                    existing.confidence = confidence
                    existing.source = source
                    existing.last_accessed = datetime.now().isoformat()
                    existing.access_count += 1
                    print(f"🔄 Memory updated (conflict resolved): [{mem_type}] {key} = {value} "
                          f"(conf {existing.confidence:.2f} → {confidence:.2f})")
                else:
                    # Existing wins — just bump access
                    existing.last_accessed = datetime.now().isoformat()
                    existing.access_count += 1
                    print(f"📎 Memory exists (kept): [{mem_type}] {key} = {existing.value} "
                          f"(conf {existing.confidence:.2f})")
                self._save()
                return existing.id
            else:
                # New entry
                import hashlib
                entry_id = hashlib.md5(
                    f"{mem_type}:{key}:{time.time()}".encode()
                ).hexdigest()[:10]

                entry = MemoryEntry(
                    id=entry_id,
                    type=mem_type,
                    key=key,
                    value=value,
                    confidence=confidence,
                    source=source,
                )
                self._entries.append(entry)
                print(f"[+] Memory stored: [{mem_type}] {key} = {value} (conf={confidence:.2f})")

                # Bridge to VectorMemory for semantic recall
                self._index_to_vector(entry)

                # Prune if over limit
                if len(self._entries) > MAX_MEMORIES:
                    self._prune()

                self._save()
                return entry_id

    def recall(self, key: str, mem_type: str = None) -> Optional[MemoryEntry]:
        """
        Recall a memory by key. Applies decay.
        Updates access timestamp.
        """
        with self._lock:
            for entry in self._entries:
                if entry.key == key and (mem_type is None or entry.type == mem_type):
                    # Apply decay
                    decayed = entry.decayed_confidence()
                    if decayed < MIN_CONFIDENCE:
                        # Memory has decayed too much — auto-prune
                        self._entries.remove(entry)
                        print(f"[~] Memory expired (decay): [{entry.type}] {entry.key}")
                        self._save()
                        return None

                    entry.confidence = decayed
                    entry.last_accessed = datetime.now().isoformat()
                    entry.access_count += 1
                    self._save()
                    return entry
        return None

    def reinforce(self, key: str, mem_type: str = None) -> None:
        """Boost confidence when a memory is used successfully."""
        with self._lock:
            for entry in self._entries:
                if entry.key == key and (mem_type is None or entry.type == mem_type):
                    old_conf = entry.confidence
                    entry.confidence = min(REINFORCE_CAP, entry.confidence + REINFORCE_BOOST)
                    entry.last_accessed = datetime.now().isoformat()
                    entry.access_count += 1
                    print(f"[+] Memory reinforced: [{entry.type}] {entry.key} "
                          f"(conf {old_conf:.2f} → {entry.confidence:.2f})")
                    self._save()
                    return

    def get_preferences(self) -> list[MemoryEntry]:
        """Returns all preference-type memories (with decay applied)."""
        return self._get_by_type("preference")

    def get_by_type(self, mem_type: str) -> list[MemoryEntry]:
        """Returns all memories of a given type."""
        return self._get_by_type(mem_type)

    def search(self, query: str) -> list[MemoryEntry]:
        """Keyword search across all memories."""
        query_lower = query.lower()
        results = []
        for entry in self._entries:
            if (query_lower in entry.key.lower() or
                    query_lower in entry.value.lower()):
                decayed = entry.decayed_confidence()
                if decayed >= MIN_CONFIDENCE:
                    entry.confidence = decayed
                    results.append(entry)
        return sorted(results, key=lambda e: e.confidence, reverse=True)

    # ─── User Control API ────────────────────────────────────

    def view_memories(self, mem_type: str = None) -> list[dict]:
        """Returns all memories as dicts for user viewing."""
        entries = self._entries if not mem_type else [
            e for e in self._entries if e.type == mem_type
        ]
        return [
            {
                "type": e.type, "key": e.key, "value": e.value,
                "confidence": round(e.decayed_confidence(), 3),
                "source": e.source, "access_count": e.access_count,
            }
            for e in entries
        ]

    def delete_memory(self, key: str, mem_type: str = None) -> bool:
        """Delete a specific memory entry."""
        with self._lock:
            for entry in self._entries:
                if entry.key == key and (mem_type is None or entry.type == mem_type):
                    self._entries.remove(entry)
                    self._save()
                    print(f"[x] Memory deleted: [{entry.type}] {entry.key}")
                    return True
        return False

    def clear_all(self) -> None:
        """Clear all memories."""
        with self._lock:
            self._entries = []
            self._save()
        print("[x] All memories cleared")

    # ─── Auto-Extraction from Conversations ──────────────────

    def extract_and_store(self, user_text: str) -> list[str]:
        """
        3-level extraction from user utterance.

        Level 1 (Explicit, ≥0.8):  "Remember this", "I prefer"
        Level 2 (Strong, 0.6-0.8): "I usually use", "my name is"
        Level 3 (Weak, <0.6):      IGNORED

        Returns list of stored memory IDs.
        """
        if not user_text or len(user_text) < 5:
            return []

        stored_ids = []
        text_lower = user_text.lower().strip()

        # Level 1: Explicit patterns
        for pattern in EXPLICIT_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                mem_id = self._extract_and_store_entry(
                    user_text, confidence=0.9, source="explicit"
                )
                if mem_id:
                    stored_ids.append(mem_id)
                return stored_ids  # One extraction per utterance

        # Level 2: Strong signal patterns
        for pattern in STRONG_SIGNAL_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                mem_id = self._extract_and_store_entry(
                    user_text, confidence=0.7, source="strong_signal"
                )
                if mem_id:
                    stored_ids.append(mem_id)
                return stored_ids

        # Level 3: Weak signal → IGNORE
        return stored_ids

    # ─── Internal Helpers ────────────────────────────────────

    def _extract_and_store_entry(
        self, text: str, confidence: float, source: str
    ) -> Optional[str]:
        """Extract key-value from text and store as memory."""
        text_lower = text.lower().strip()

        # Try to detect memory type and extract key/value
        mem_type = "context"
        key = ""
        value = text.strip()

        # Preference detection: "I prefer/like/love/hate X"
        pref_match = re.search(
            r"\bI\s+(?:prefer|like|love|hate|dislike|always\s+use|never\s+use)\s+(.+)",
            text, re.IGNORECASE
        )
        if pref_match:
            mem_type = "preference"
            value = pref_match.group(1).strip().rstrip(".")
            key = self._infer_key(value)

        # Person detection: "my name is X", "I'm called X"
        name_match = re.search(
            r"\b(?:my\s+name\s+is|I'?m\s+called|I\s+go\s+by)\s+(.+)",
            text, re.IGNORECASE
        )
        if name_match:
            mem_type = "person"
            key = "user_name"
            value = name_match.group(1).strip().rstrip(".")

        # Habit detection: "I usually/typically/normally X"
        habit_match = re.search(
            r"\bI\s+(?:usually|typically|normally|always)\s+(.+)",
            text, re.IGNORECASE
        )
        if habit_match and mem_type == "context":
            mem_type = "habit"
            value = habit_match.group(1).strip().rstrip(".")
            key = self._infer_key(value)

        # Fact detection: "remember that X"
        fact_match = re.search(
            r"\bremember\s+(?:that|this)\s*[:\-]?\s*(.+)",
            text, re.IGNORECASE
        )
        if fact_match:
            mem_type = "fact"
            value = fact_match.group(1).strip().rstrip(".")
            key = self._infer_key(value)

        # Identity detection: "I'm a developer/student"
        identity_match = re.search(
            r"\bI'?m\s+(?:a|an)\s+(.+?)(?:\s+(?:who|and|that)|$)",
            text, re.IGNORECASE
        )
        if identity_match and mem_type == "context":
            mem_type = "fact"
            key = "identity"
            value = identity_match.group(1).strip().rstrip(".")

        # Work tools: "I work with/code in X"
        tool_match = re.search(
            r"\bI\s+(?:work|code)\s+(?:in|with)\s+(.+)",
            text, re.IGNORECASE
        )
        if tool_match and mem_type == "context":
            mem_type = "preference"
            key = "work_tool"
            value = tool_match.group(1).strip().rstrip(".")

        if not key:
            key = f"note_{int(time.time())}"

        return self.store(mem_type, key, value, confidence, source)

    def _infer_key(self, value: str) -> str:
        """Infer a storage key from a value string."""
        # Common tool/app names
        tool_words = {
            "vscode", "vim", "terminal", "chrome", "firefox",
            "safari", "brave", "spotify", "slack", "discord",
            "dark mode", "light mode",
        }
        val_lower = value.lower()
        for tool in tool_words:
            if tool in val_lower:
                return tool.replace(" ", "_")

        # Use first 2 meaningful words
        words = [w for w in value.split() if len(w) > 2][:2]
        return "_".join(words).lower() if words else "general"

    def _find(self, mem_type: str, key: str) -> Optional[MemoryEntry]:
        """Find entry by type + key."""
        for entry in self._entries:
            if entry.type == mem_type and entry.key == key:
                return entry
        return None

    def _get_by_type(self, mem_type: str) -> list[MemoryEntry]:
        """Get all entries of a type, applying decay and pruning expired."""
        results = []
        expired = []
        for entry in self._entries:
            if entry.type == mem_type:
                decayed = entry.decayed_confidence()
                if decayed < MIN_CONFIDENCE:
                    expired.append(entry)
                else:
                    entry.confidence = decayed
                    results.append(entry)
        # Prune expired
        for e in expired:
            self._entries.remove(e)
        if expired:
            self._save()
        return sorted(results, key=lambda e: e.confidence, reverse=True)

    def _is_sensitive(self, text: str) -> bool:
        """Check if text contains sensitive information."""
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in SENSITIVE_PATTERNS)

    def _prune(self) -> None:
        """Remove lowest-confidence entries to stay under MAX_MEMORIES."""
        # Apply decay to all, remove expired
        active = []
        for entry in self._entries:
            decayed = entry.decayed_confidence()
            if decayed >= MIN_CONFIDENCE:
                entry.confidence = decayed
                active.append(entry)
        # Sort by confidence, keep top MAX_MEMORIES
        active.sort(key=lambda e: e.confidence, reverse=True)
        self._entries = active[:MAX_MEMORIES]

    def _index_to_vector(self, entry: MemoryEntry) -> None:
        """Bridge: index memory into VectorMemory for semantic recall."""
        try:
            from core.vector_memory import get_vector_memory
            vm = get_vector_memory()
            text = f"[{entry.type}] {entry.key}: {entry.value}"
            vm.store(text, metadata={
                "type": entry.type,
                "key": entry.key,
                "source": "continuous_memory",
                "confidence": entry.confidence,
            }, doc_id=f"cm_{entry.id}")
        except Exception:
            pass  # VectorMemory not available — skip silently

    # ─── Persistence ─────────────────────────────────────────

    def _load(self) -> None:
        """Load memories from disk."""
        if os.path.exists(MEMORY_PATH):
            try:
                with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = [MemoryEntry.from_dict(d) for d in data]
            except Exception as e:
                print(f"⚠️  Continuous memory load error: {e}")
                self._entries = []

    def _save(self) -> None:
        """Save memories to disk."""
        os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
        try:
            data = [e.to_dict() for e in self._entries]
            with open(MEMORY_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Continuous memory save error: {e}")

    @property
    def count(self) -> int:
        return len(self._entries)


# ─── Singleton ───────────────────────────────────────────────
_cm_instance: Optional[ContinuousMemory] = None
_cm_lock = threading.Lock()


def get_continuous_memory() -> ContinuousMemory:
    """Returns the global ContinuousMemory singleton."""
    global _cm_instance
    if _cm_instance is None:
        with _cm_lock:
            if _cm_instance is None:
                _cm_instance = ContinuousMemory()
    return _cm_instance


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  CONTINUOUS MEMORY TEST")
    print("=" * 60)

    mem = ContinuousMemory()
    mem.clear_all()

    # Test 1: Explicit store
    print("\n── Store ──")
    mem.store("preference", "editor", "VSCode", confidence=0.9, source="explicit")
    mem.store("person", "user_name", "Aariyan", confidence=1.0, source="explicit")
    mem.store("habit", "morning_routine", "open terminal at 10 AM", confidence=0.7)

    # Test 2: Conflict resolution (higher confidence wins)
    print("\n── Conflict Resolution ──")
    mem.store("preference", "editor", "Cursor", confidence=0.95, source="explicit")

    # Test 3: Conflict resolution (lower confidence loses)
    mem.store("preference", "editor", "Vim", confidence=0.5, source="strong_signal")

    # Test 4: Recall
    print("\n── Recall ──")
    editor = mem.recall("editor", "preference")
    print(f"  Editor: {editor.value if editor else 'None'}")

    # Test 5: Reinforcement
    print("\n── Reinforce ──")
    mem.reinforce("editor", "preference")

    # Test 6: Auto-extraction
    print("\n── Auto-Extraction ──")
    mem.extract_and_store("Remember that I have a meeting at 3 PM")
    mem.extract_and_store("I prefer dark mode")
    mem.extract_and_store("I usually code in Python")
    mem.extract_and_store("open vscode")  # Weak signal → should be ignored

    # Test 7: View all
    print("\n── All Memories ──")
    for m in mem.view_memories():
        print(f"  [{m['type']}] {m['key']} = {m['value']} (conf={m['confidence']:.2f})")

    # Test 8: Sensitive data block
    print("\n── Sensitive Data ──")
    result = mem.store("fact", "api_key", "sk-12345")
    print(f"  Sensitive store result: {result}")

    # Test 9: Delete
    print("\n── Delete ──")
    mem.delete_memory("user_name", "person")

    print(f"\n  Total memories: {mem.count}")
    print("\n✅ Continuous memory test passed!")
