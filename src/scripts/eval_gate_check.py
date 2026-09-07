"""
Scores an eval run (produced by `run-eval --out <path>`) and gates it against
eval_baseline.json. Aggregate score = mean of success_rate and
correct_refusal_rate (both as percentages) -- avg_tool_calls is reported but
not gated on, since it varies run-to-run even with no code change (see
README's known limitations).

Usage: poetry run python -m scripts.eval_gate_check <eval_run.json> [--out eval_result.json]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def score_eval_run(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload["summary"]
    success_rate = summary.get("success_rate")
    correct_refusal_rate = summary.get("correct_refusal_rate")

    rates = [r for r in (success_rate, correct_refusal_rate) if r is not None]
    if not rates:
        raise SystemExit("eval run has neither success_rate nor correct_refusal_rate — nothing to score")

    score_pct = sum(rates) / len(rates) * 100.0

    return {
        "n": summary.get("n"),
        "success_rate": success_rate,
        "correct_refusal_rate": correct_refusal_rate,
        "avg_tool_calls": summary.get("avg_tool_calls"),
        "score_pct": score_pct,
    }


def _commit_sha(explicit: str | None) -> str:
    if explicit:
        return explicit
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha:
        return env_sha
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Score an eval run and gate it against eval_baseline.json")
    ap.add_argument("eval_run_json", help="Path to a JSON file produced by `run-eval --out ...`")
    ap.add_argument("--baseline", default="eval_baseline.json")
    ap.add_argument("--tolerance-pct", type=float, default=float(os.getenv("EVAL_TOLERANCE_PCT", "2.0")))
    ap.add_argument("--out", default="eval_result.json")
    ap.add_argument("--commit-sha", default=None)
    args = ap.parse_args()

    payload = json.loads(Path(args.eval_run_json).read_text(encoding="utf-8"))
    scored = score_eval_run(payload)

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        raise SystemExit(f"Missing baseline file: {baseline_path}. Run scripts/update_eval_baseline.py first.")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_score_pct = float(baseline["score_pct"])

    threshold_pct = baseline_score_pct - args.tolerance_pct
    passed = scored["score_pct"] >= threshold_pct

    result = {
        **scored,
        "commit_sha": _commit_sha(args.commit_sha),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_score_pct": baseline_score_pct,
        "tolerance_pct": args.tolerance_pct,
        "threshold_pct": threshold_pct,
        "delta_pct": scored["score_pct"] - baseline_score_pct,
        "passed": passed,
    }

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    status = "PASS" if passed else "FAIL"
    print(
        f"[{status}] score={scored['score_pct']:.2f}% "
        f"(success_rate={scored['success_rate']}, correct_refusal_rate={scored['correct_refusal_rate']}, n={scored['n']}) "
        f"baseline={baseline_score_pct:.2f}% threshold={threshold_pct:.2f}% delta={result['delta_pct']:+.2f}pp"
    )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
