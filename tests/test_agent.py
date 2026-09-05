"""
Tests for the agent loop's control flow -- no real OpenAI calls, no real DB.
The OpenAI client is a hand-written fake (matching agent.ask()'s expected
shape exactly) rather than a generic mock, so a shape mismatch fails loudly
instead of silently returning a MagicMock.
"""
import json
from dataclasses import dataclass

import app.agent as agent_module
from app.agent import REFUSAL_MESSAGE, ask


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction
    type: str = "function"


@dataclass
class FakeMessage:
    content: str | None = None
    tool_calls: list[FakeToolCall] | None = None

    def model_dump(self, exclude_none: bool = True) -> dict:
        d = {"role": "assistant", "content": self.content, "tool_calls": self.tool_calls}
        return {k: v for k, v in d.items() if v is not None} if exclude_none else d


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeResponse:
    choices: list[FakeChoice]


class FakeCompletions:
    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs) -> FakeResponse:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeOpenAIClient:
    def __init__(self, responses: list[FakeResponse]):
        self.completions = FakeCompletions(responses)
        self.chat = self


def _final(content: str) -> FakeResponse:
    return FakeResponse(choices=[FakeChoice(message=FakeMessage(content=content))])


def _tool_call(name: str, arguments: dict, call_id: str = "call_1") -> FakeResponse:
    tc = FakeToolCall(id=call_id, function=FakeFunction(name=name, arguments=json.dumps(arguments)))
    return FakeResponse(choices=[FakeChoice(message=FakeMessage(content=None, tool_calls=[tc]))])


def test_ask_returns_final_answer_with_no_tool_calls():
    client = FakeOpenAIClient([_final("The average order value is R$120.")])

    result = ask("What's the average order value?", client=client)

    assert result.answer == "The average order value is R$120."
    assert result.iterations_used == 1
    assert result.trace == []


def test_ask_executes_tool_call_then_returns_final_answer(monkeypatch):
    monkeypatch.setitem(
        agent_module.TOOLS_BY_NAME,
        "sql_query",
        lambda query: {"columns": ["n"], "rows": [(42,)], "row_count": 1},
    )
    client = FakeOpenAIClient(
        [
            _tool_call("sql_query", {"query": "SELECT count(*) AS n FROM orders"}),
            _final("There are 42 orders."),
        ]
    )

    result = ask("How many orders are there?", client=client)

    assert result.answer == "There are 42 orders."
    assert result.iterations_used == 2
    assert len(result.trace) == 1
    assert result.trace[0]["tool"] == "sql_query"
    assert result.trace[0]["result"]["rows"] == [(42,)]


def test_ask_refuses_honestly_after_max_iterations(monkeypatch):
    monkeypatch.setitem(
        agent_module.TOOLS_BY_NAME,
        "sql_query",
        lambda query: {"columns": [], "rows": [], "row_count": 0},
    )
    # Model keeps calling the tool and never gives a final answer.
    responses = [_tool_call("sql_query", {"query": "SELECT 1"}, call_id=f"call_{i}") for i in range(5)]
    client = FakeOpenAIClient(responses)

    result = ask("An unanswerable question", client=client, max_iterations=3)

    assert result.answer == REFUSAL_MESSAGE
    assert result.iterations_used == 3
    assert len(result.trace) == 3
    assert len(client.completions.calls) == 3


def test_ask_returns_error_for_unknown_tool(monkeypatch):
    client = FakeOpenAIClient(
        [
            _tool_call("does_not_exist", {}),
            _final("done"),
        ]
    )

    result = ask("question", client=client)

    assert result.trace[0]["result"] == {"error": "Unknown tool: does_not_exist"}
