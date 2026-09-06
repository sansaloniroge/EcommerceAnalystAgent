"""
Unit tests for the calculator tool -- pure AST evaluation, no DB, no
network. Adversarial cases here matter more than the happy path: the
expression string comes from the model, so anything beyond numeric
literals + arithmetic operators must be rejected, not silently ignored.
"""
from app.tools.calculator import run_calculator


def test_run_calculator_evaluates_basic_arithmetic():
    assert run_calculator("2 + 3 * 4") == {"result": 14}


def test_run_calculator_evaluates_a_percentage_change():
    result = run_calculator("(120.5 - 100) / 100 * 100")
    assert result["result"] == 20.5


def test_run_calculator_handles_parentheses_and_negative_numbers():
    assert run_calculator("-(3 + 4)") == {"result": -7}


def test_run_calculator_handles_exponentiation():
    assert run_calculator("2 ** 10") == {"result": 1024}


def test_run_calculator_returns_error_for_division_by_zero():
    result = run_calculator("1 / 0")
    assert "error" in result


def test_run_calculator_rejects_a_name_reference():
    result = run_calculator("__import__('os').system('echo hi')")
    assert "error" in result


def test_run_calculator_rejects_a_function_call():
    result = run_calculator("abs(-5)")
    assert "error" in result


def test_run_calculator_rejects_an_attribute_access():
    result = run_calculator("(1).__class__")
    assert "error" in result


def test_run_calculator_rejects_a_string_literal():
    result = run_calculator("'a' + 'b'")
    assert "error" in result


def test_run_calculator_rejects_invalid_syntax():
    result = run_calculator("2 + ")
    assert "error" in result


def test_run_calculator_rejects_boolean_literal():
    # Python treats bool as a subclass of int -- must not sneak through as 0/1.
    result = run_calculator("True")
    assert "error" in result


def test_run_calculator_rejects_multiple_statements():
    result = run_calculator("1 + 1; 2 + 2")
    assert "error" in result
