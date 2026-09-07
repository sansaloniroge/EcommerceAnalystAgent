import json
import sys

import pytest

from scripts.eval_gate_check import main, score_eval_run


def _run_payload(success_rate: float | None, correct_refusal_rate: float | None, n: int = 5) -> dict:
    return {
        "summary": {
            "n": n,
            "success_rate": success_rate,
            "correct_refusal_rate": correct_refusal_rate,
            "avg_tool_calls": 1.2,
        },
        "results": [],
    }


def test_score_eval_run_averages_both_rates():
    scored = score_eval_run(_run_payload(1.0, 1.0))
    assert scored["score_pct"] == pytest.approx(100.0)


def test_score_eval_run_handles_partial_rates():
    scored = score_eval_run(_run_payload(0.5, None))
    assert scored["score_pct"] == pytest.approx(50.0)


def test_score_eval_run_raises_with_no_rates():
    with pytest.raises(SystemExit):
        score_eval_run(_run_payload(None, None))


def _run_cli(run_path, baseline_path, out_path, tolerance="2.0") -> int:
    argv = sys.argv
    sys.argv = [
        "eval_gate_check",
        str(run_path),
        "--baseline",
        str(baseline_path),
        "--tolerance-pct",
        tolerance,
        "--out",
        str(out_path),
    ]
    try:
        return main()
    finally:
        sys.argv = argv


def test_gate_check_cli_passes_within_tolerance(tmp_path):
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(_run_payload(1.0, 1.0)), encoding="utf-8")
    baseline_path = tmp_path / "eval_baseline.json"
    baseline_path.write_text(json.dumps({"score_pct": 99.0}), encoding="utf-8")
    out_path = tmp_path / "eval_result.json"

    exit_code = _run_cli(run_path, baseline_path, out_path)

    assert exit_code == 0
    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["passed"] is True
    assert result["score_pct"] == pytest.approx(100.0)


def test_gate_check_cli_fails_below_tolerance(tmp_path):
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(_run_payload(0.5, 0.5)), encoding="utf-8")
    baseline_path = tmp_path / "eval_baseline.json"
    baseline_path.write_text(json.dumps({"score_pct": 99.0}), encoding="utf-8")
    out_path = tmp_path / "eval_result.json"

    exit_code = _run_cli(run_path, baseline_path, out_path)

    assert exit_code == 1
    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["passed"] is False
