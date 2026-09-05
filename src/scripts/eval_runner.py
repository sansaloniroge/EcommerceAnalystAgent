#!/usr/bin/env python3
"""
Runs the agent against eval/dataset.json and grades each answer by objective
correctness -- not an LLM-as-judge. Ground truth was computed by hand, once,
with direct SQL against the real loaded dataset (see the phase's Notion
page / commit for the queries used), then frozen into the dataset file.

Usage: poetry run run-eval [--dataset eval/dataset.json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from app.agent import REFUSAL_MESSAGE, AgentResult, ask

REPO_ROOT = Path(__file__).resolve().parents[2]

_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")

_REFUSAL_PHRASES = [
    "cannot be determined",
    "can't be determined",
    "cannot determine",
    "can't determine",
    "cannot answer",
    "can't answer",
    "don't have",
    "do not have",
    "not available",
    "no data",
    "not possible",
    "unable to",
    "doesn't contain",
    "does not contain",
    "isn't tracked",
    "is not tracked",
    "no information",
    "not captured",
    "not present in",
]


def _extract_numbers(text: str) -> list[float]:
    numbers = []
    for match in _NUMBER_RE.findall(text):
        try:
            numbers.append(float(match.replace(",", "")))
        except ValueError:
            continue
    return numbers


def grade_numeric(answer: str, expected: float, tolerance: float) -> bool:
    return any(abs(n - expected) <= tolerance for n in _extract_numbers(answer))


def grade_text(answer: str, required_substrings: list[str]) -> bool:
    lowered = answer.lower()
    return all(s.lower() in lowered for s in required_substrings)


def grade_refusal(answer: str) -> bool:
    if answer == REFUSAL_MESSAGE:
        return True
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


def grade(question: dict[str, Any], result: AgentResult) -> bool:
    q_type = question["type"]
    if q_type == "numeric":
        return grade_numeric(result.answer, question["expected"], question["tolerance"])
    if q_type == "text":
        return grade_text(result.answer, question["required_substrings"])
    if q_type == "refusal":
        return grade_refusal(result.answer)
    raise ValueError(f"unknown question type: {q_type!r}")


def run_eval(
    dataset: list[dict[str, Any]], ask_fn: Callable[[str], AgentResult] = ask
) -> list[dict[str, Any]]:
    results = []
    for question in dataset:
        result = ask_fn(question["question"])
        results.append(
            {
                "id": question["id"],
                "type": question["type"],
                "question": question["question"],
                "answer": result.answer,
                "tool_calls": len(result.trace),
                "iterations_used": result.iterations_used,
                "passed": grade(question, result),
            }
        )
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    factual = [r for r in results if r["type"] in ("numeric", "text")]
    refusals = [r for r in results if r["type"] == "refusal"]
    return {
        "n": len(results),
        "success_rate": (sum(r["passed"] for r in factual) / len(factual)) if factual else None,
        "correct_refusal_rate": (sum(r["passed"] for r in refusals) / len(refusals)) if refusals else None,
        "avg_tool_calls": sum(r["tool_calls"] for r in results) / len(results) if results else None,
    }


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="eval/dataset.json", help="Path to the eval question set")
    args = ap.parse_args()

    dataset_path = (REPO_ROOT / args.dataset) if not Path(args.dataset).is_absolute() else Path(args.dataset)
    with open(dataset_path) as f:
        dataset = json.load(f)

    results = run_eval(dataset)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['id']} ({r['tool_calls']} tool calls): {r['answer']}")

    summary = summarize(results)
    print()
    print(f"n={summary['n']}")
    print(f"success_rate={summary['success_rate']:.2%}" if summary["success_rate"] is not None else "success_rate=n/a")
    print(
        f"correct_refusal_rate={summary['correct_refusal_rate']:.2%}"
        if summary["correct_refusal_rate"] is not None
        else "correct_refusal_rate=n/a"
    )
    print(f"avg_tool_calls={summary['avg_tool_calls']:.2f}" if summary["avg_tool_calls"] is not None else "avg_tool_calls=n/a")


if __name__ == "__main__":
    main()
