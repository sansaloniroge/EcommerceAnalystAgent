"""
Unit tests for eval_runner's grading logic and orchestration -- no real
OpenAI/DB calls. run_eval takes an injectable ask_fn (same pattern as
agent.ask's injectable client), so these test the runner's plumbing with a
fake agent instead of a fake OpenAI client.
"""
from app.agent import REFUSAL_MESSAGE, AgentResult
from scripts.eval_runner import grade_numeric, grade_refusal, grade_text, run_eval, summarize


def test_grade_numeric_accepts_a_value_within_tolerance():
    assert grade_numeric("The average is about 137.5 BRL.", expected=137.04, tolerance=1.0)


def test_grade_numeric_rejects_a_value_outside_tolerance():
    assert not grade_numeric("The average is about 200 BRL.", expected=137.04, tolerance=1.0)


def test_grade_numeric_handles_comma_thousands_separators():
    assert grade_numeric("There are 99,441 orders.", expected=99441, tolerance=0)


def test_grade_numeric_accepts_a_percentage_among_other_numbers():
    answer = "Out of 99441 orders, 96478 are delivered -- about 97.02%."
    assert grade_numeric(answer, expected=97.02, tolerance=0.5)


def test_grade_text_requires_all_substrings_case_insensitive():
    assert grade_text("The top category is Health_Beauty by revenue.", ["health", "beauty"])
    assert not grade_text("The top category is watches_gifts.", ["health", "beauty"])


def test_grade_refusal_accepts_the_exact_refusal_message():
    assert grade_refusal(REFUSAL_MESSAGE)


def test_grade_refusal_accepts_a_refusal_phrase():
    assert grade_refusal("I don't have cost data, so I can't compute profit margin.")


def test_grade_refusal_accepts_a_does_not_include_phrasing():
    # Real model output that motivated adding this phrase -- "cannot calculate"
    # and "does not include" weren't in the original phrase list.
    assert grade_refusal(
        "The dataset does not include cost or margin data for products, "
        "only prices and freight values. Without cost information, I cannot "
        "calculate profit margin."
    )


def test_grade_refusal_rejects_a_confident_fabricated_answer():
    assert not grade_refusal("The profit margin was approximately 23%.")


def test_run_eval_grades_each_question_with_the_injected_agent():
    dataset = [
        {"id": "q1", "question": "how many orders?", "type": "numeric", "expected": 99441, "tolerance": 0},
        {"id": "q2", "question": "what's the profit margin?", "type": "refusal"},
    ]

    def fake_ask(question: str) -> AgentResult:
        if "orders" in question:
            return AgentResult(answer="There are 99441 orders.", trace=[{"tool": "sql_query"}], iterations_used=2)
        return AgentResult(answer="I don't have cost data for that.", trace=[], iterations_used=1)

    results = run_eval(dataset, ask_fn=fake_ask)

    assert results[0]["passed"] is True
    assert results[0]["tool_calls"] == 1
    assert results[1]["passed"] is True
    assert results[1]["tool_calls"] == 0


def test_summarize_computes_rates_separately_for_factual_and_refusal_questions():
    results = [
        {"type": "numeric", "passed": True, "tool_calls": 2},
        {"type": "numeric", "passed": False, "tool_calls": 1},
        {"type": "refusal", "passed": True, "tool_calls": 0},
    ]

    summary = summarize(results)

    assert summary["n"] == 3
    assert summary["success_rate"] == 0.5
    assert summary["correct_refusal_rate"] == 1.0
    assert summary["avg_tool_calls"] == 1.0
