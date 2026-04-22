#!/usr/bin/env python3
"""
Run intent classification against evals/command_benchmark.json.

Usage (from repo root):
    python evals/run_command_eval.py
    python evals/run_command_eval.py --path evals/command_benchmark.json --min-confidence 0.35
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root on path (same pattern as test_encoder.py)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("cases") or [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Command understanding benchmark (fast intent).")
    ap.add_argument(
        "--path",
        default=str(ROOT / "evals" / "command_benchmark.json"),
        help="Path to benchmark JSON",
    )
    ap.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Count as failure if best confidence is below this threshold",
    )
    ap.add_argument("--no-init", action="store_true", help="Skip cross-encoder initialization")
    args = ap.parse_args()

    from core.fast_intent import initialize, classify

    if not args.no_init:
        initialize()

    cases = _load_cases(Path(args.path))
    if not cases:
        print("No cases in benchmark.", file=sys.stderr)
        return 2

    passed = 0
    failed: list[tuple[str, str, str, float]] = []

    for c in cases:
        utterance = c.get("utterance") or ""
        expected = c.get("expected_action") or ""
        cid = c.get("id", utterance[:32])
        result = classify(utterance)
        ok = result.action == expected and result.confidence >= args.min_confidence
        if ok:
            passed += 1
        else:
            failed.append((cid, expected, result.action, result.confidence))

    total = len(cases)
    print(f"Benchmark: {args.path}")
    print(f"Passed: {passed}/{total} (min_confidence={args.min_confidence})")
    for cid, exp, got, conf in failed:
        print(f"  FAIL [{cid}] expected={exp!r} got={got!r} conf={conf:.3f}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
