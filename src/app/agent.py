from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageFunctionToolCall

from app.schema_doc import SYSTEM_PROMPT
from app.tools.calculator import TOOL_SCHEMA as CALCULATOR_TOOL_SCHEMA
from app.tools.calculator import run_calculator
from app.tools.sql_query import TOOL_SCHEMA as SQL_QUERY_TOOL_SCHEMA
from app.tools.sql_query import run_sql_query

MODEL = "gpt-4.1-mini"
MAX_ITERATIONS = 6

REFUSAL_MESSAGE = (
    "I couldn't reach a confident answer within the allotted number of steps "
    "for this question. Rather than guess, I'm stopping here -- see the trace "
    "for what I tried."
)

TOOL_SCHEMAS = [SQL_QUERY_TOOL_SCHEMA, CALCULATOR_TOOL_SCHEMA]

TOOLS_BY_NAME: dict[str, Callable[..., dict[str, Any]]] = {
    "sql_query": run_sql_query,
    "calculator": run_calculator,
}


@dataclass
class AgentResult:
    answer: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    iterations_used: int = 0


def _run_tool_call(tool_call: ChatCompletionMessageFunctionToolCall) -> dict[str, Any]:
    name = tool_call.function.name
    tool_fn = TOOLS_BY_NAME.get(name)
    if tool_fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        arguments = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid arguments JSON: {e}"}
    return tool_fn(**arguments)


def ask(question: str, client: OpenAI | None = None, max_iterations: int = MAX_ITERATIONS) -> AgentResult:
    """
    Hand-rolled tool-calling loop -- sql_query and calculator. See PORTFOLIO
    design doc / README for the full loop design and guardrails.
    """
    client = client or OpenAI()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    trace: list[dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,  # type: ignore[arg-type]
            tools=TOOL_SCHEMAS,
            temperature=0,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return AgentResult(answer=message.content or "", trace=trace, iterations_used=iteration)

        for tool_call in message.tool_calls:
            if tool_call.type != "function":
                # We only ever register function-type tools (see TOOL_SCHEMA);
                # a custom-type call would mean a tool we didn't define.
                result = {"error": f"Unsupported tool call type: {tool_call.type}"}
                trace.append({"iteration": iteration, "tool": tool_call.type, "arguments": None, "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)}
                )
                continue

            result = _run_tool_call(tool_call)
            trace.append(
                {
                    "iteration": iteration,
                    "tool": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                    "result": result,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return AgentResult(answer=REFUSAL_MESSAGE, trace=trace, iterations_used=max_iterations)
