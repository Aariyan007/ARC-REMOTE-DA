"""
Enhanced Logger — records all commands, actions, latency, confidence,
intent source, errors, and retries for debugging and analytics.

Extends the original logger with production-grade observability.
"""

import json
import os
from datetime import datetime


# ─── Settings ────────────────────────────────────────────────
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
# ─────────────────────────────────────────────────────────────


def _get_log_file() -> str:
    """Returns today's log file path. Creates logs/ folder if needed."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOGS_DIR, f"{today}.json")


def _load_today() -> list:
    """Loads today's log file. Returns empty list if doesn't exist yet."""
    path = _get_log_file()
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def log_interaction(
    you_said: str,
    action_taken: str,
    was_understood: bool,
    sent_to_gemini: bool = False,
    gemini_response: str = None,
    # ── New production fields ────────────────────────────────
    latency_ms: float = None,
    intent_source: str = None,    # "fast_engine" | "learned" | "gemini" | "cache"
    confidence: float = None,
    error: str = None,
    retry_count: int = 0,
    normalized_text: str = None,
    params: dict = None,
    spoken_text: str = None,      # NEW: what Jarvis actually said via TTS
):
    """
    Logs a single Jarvis interaction to today's JSON file.

    Args:
        you_said:        Raw text Whisper heard from you
        action_taken:    What Jarvis did ("open_vscode", "tell_time", etc)
        was_understood:  True if router matched it, False if unknown
        sent_to_gemini:  True if Gemini was used as fallback
        gemini_response: What Gemini returned (if used)
        latency_ms:      Time from command received to action executed
        intent_source:   Where the intent came from
        confidence:      Float score from intent engine (0.0-1.0)
        error:           Exception message if action failed
        retry_count:     How many retries were needed
        normalized_text: The cleaned/normalized version of you_said
        params:          Resolved parameters for the action
        spoken_text:     What Jarvis actually said via TTS (the real output)
    """
    entry = {
        "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "you_said":        you_said,
        "normalized":      normalized_text,
        "action_taken":    action_taken,
        "params":          params,
        "was_understood":  was_understood,
        "sent_to_gemini":  sent_to_gemini,
        "gemini_response": gemini_response,
        "spoken_text":     spoken_text,
        "latency_ms":      round(latency_ms, 1) if latency_ms is not None else None,
        "intent_source":   intent_source,
        "confidence":      round(confidence, 3) if confidence is not None else None,
        "error":           error,
        "retry_count":     retry_count,
    }

    # Remove None values to keep logs clean
    entry = {k: v for k, v in entry.items() if v is not None}

    entries = _load_today()
    entries.append(entry)

    with open(_get_log_file(), "w") as f:
        json.dump(entries, f, indent=2)

    # Console output
    source_tag = f" [{intent_source}]" if intent_source else ""
    conf_tag   = f" conf={confidence:.2f}" if confidence is not None else ""
    lat_tag    = f" {latency_ms:.0f}ms" if latency_ms is not None else ""
    err_tag    = f" ⚠️{error}" if error else ""

    print(f"📝 Logged: '{you_said}' → {action_taken}{source_tag}{conf_tag}{lat_tag}{err_tag}")


def get_todays_stats() -> dict:
    """
    Returns a quick summary of today's usage.
    Useful for seeing patterns over time.
    """
    entries = _load_today()
    if not entries:
        return {"total": 0}

    understood   = sum(1 for e in entries if e.get("was_understood"))
    used_gemini  = sum(1 for e in entries if e.get("sent_to_gemini"))
    actions      = [e["action_taken"] for e in entries]
    most_used    = max(set(actions), key=actions.count) if actions else None

    return {
        "total":           len(entries),
        "understood":      understood,
        "failed":          len(entries) - understood,
        "used_gemini":     used_gemini,
        "most_used":       most_used,
        "all_actions":     actions,
    }


def get_performance_stats() -> dict:
    """
    Returns performance analytics for today.
    Shows how fast the system is and where time is spent.
    """
    entries = _load_today()
    if not entries:
        return {"total": 0}

    latencies = [e["latency_ms"] for e in entries if e.get("latency_ms") is not None]
    confidences = [e["confidence"] for e in entries if e.get("confidence") is not None]
    sources = [e.get("intent_source", "unknown") for e in entries]
    errors = [e for e in entries if e.get("error")]

    source_counts = {}
    for s in sources:
        source_counts[s] = source_counts.get(s, 0) + 1

    return {
        "total_commands":     len(entries),
        "avg_latency_ms":    round(sum(latencies) / len(latencies), 1) if latencies else None,
        "min_latency_ms":    round(min(latencies), 1) if latencies else None,
        "max_latency_ms":    round(max(latencies), 1) if latencies else None,
        "avg_confidence":    round(sum(confidences) / len(confidences), 3) if confidences else None,
        "intent_sources":    source_counts,
        "fast_engine_rate":  f"{source_counts.get('fast_engine', 0) / len(entries) * 100:.0f}%" if entries else "0%",
        "gemini_fallback_rate": f"{source_counts.get('gemini', 0) / len(entries) * 100:.0f}%" if entries else "0%",
        "error_count":       len(errors),
        "errors":            [{"action": e["action_taken"], "error": e["error"]} for e in errors[:5]],
    }


def print_todays_summary():
    """Prints a readable summary of today's Jarvis usage."""
    stats = get_todays_stats()
    perf  = get_performance_stats()

    print("\n" + "=" * 50)
    print("  TODAY'S JARVIS SUMMARY")
    print("=" * 50)
    print(f"  Total commands:      {stats.get('total', 0)}")
    print(f"  Understood:          {stats.get('understood', 0)}")
    print(f"  Failed:              {stats.get('failed', 0)}")
    print(f"  Used Gemini:         {stats.get('used_gemini', 0)}")
    print(f"  Most used command:   {stats.get('most_used', 'none')}")

    if perf.get("avg_latency_ms") is not None:
        print(f"\n  ⚡ Performance:")
        print(f"    Avg latency:       {perf['avg_latency_ms']}ms")
        print(f"    Min latency:       {perf['min_latency_ms']}ms")
        print(f"    Max latency:       {perf['max_latency_ms']}ms")
        print(f"    Avg confidence:    {perf.get('avg_confidence', 'N/A')}")
        print(f"    Fast engine rate:  {perf.get('fast_engine_rate', 'N/A')}")
        print(f"    Gemini fallback:   {perf.get('gemini_fallback_rate', 'N/A')}")

    if perf.get("error_count", 0) > 0:
        print(f"\n  ⚠️ Errors: {perf['error_count']}")
        for err in perf.get("errors", []):
            print(f"    - {err['action']}: {err['error']}")

    print("=" * 50 + "\n")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing enhanced logger...\n")

    log_interaction(
        you_said="yo open my thing",
        action_taken="open_vscode",
        was_understood=True,
        sent_to_gemini=False,
        latency_ms=12.5,
        intent_source="fast_engine",
        confidence=0.92,
        normalized_text="open vscode",
    )
    log_interaction(
        you_said="hey how are you",
        action_taken="chat_response",
        was_understood=False,
        sent_to_gemini=True,
        gemini_response="I'm doing great!",
        latency_ms=850.0,
        intent_source="gemini",
        confidence=0.35,
    )
    log_interaction(
        you_said="what time is it",
        action_taken="tell_time",
        was_understood=True,
        sent_to_gemini=False,
        latency_ms=8.2,
        intent_source="fast_engine",
        confidence=0.97,
    )

    print_todays_summary()
    print("\n📊 Performance stats:")
    print(json.dumps(get_performance_stats(), indent=2))