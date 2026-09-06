from __future__ import annotations

import ast
import operator
from typing import Any, Callable

from openai.types.chat import ChatCompletionFunctionToolParam

# Roadmap step 4: a calculator tool so the model computes percentages/growth
# rates via a real evaluation instead of doing arithmetic in its head (a
# known source of small, confident-sounding errors in LLM output).

TOOL_SCHEMA: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": (
            "Evaluate a single arithmetic expression -- numbers, +, -, *, /, ** and "
            "parentheses. Use this for any arithmetic on numbers you got from sql_query "
            "(percentages, growth rates, ratios) instead of computing it yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "An arithmetic expression, e.g. '(120.5 - 100) / 100 * 100'.",
                },
            },
            "required": ["expression"],
        },
    },
}

_BINARY_OPERATORS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type, Callable[[float], float]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    # Whitelist-based: only numeric literals and the arithmetic operators
    # above are ever evaluated. Never falls through to Python's eval() on
    # the raw string -- the expression comes from the model, not a trusted
    # caller, so arbitrary names/calls/attributes must not be reachable.
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        binary_op = _BINARY_OPERATORS.get(type(node.op))
        if binary_op is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return binary_op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        unary_op = _UNARY_OPERATORS.get(type(node.op))
        if unary_op is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return unary_op(_eval_node(node.operand))
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def run_calculator(expression: str) -> dict[str, Any]:
    """
    Evaluates `expression` as pure arithmetic. Never raises -- returns
    {"error": ...} so the agent loop can feed the failure back to the model.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
    except ZeroDivisionError:
        return {"error": "Division by zero."}
    except (SyntaxError, ValueError) as e:
        return {"error": f"Invalid expression: {e}"}
    return {"result": result}
