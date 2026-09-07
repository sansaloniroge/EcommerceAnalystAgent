"""
Tests for the LangGraph implementation's control flow -- same fake-OpenAI-client
approach as tests/test_agent.py (a hand-written fake matching the exact shape
`agent_langgraph.ask_langgraph()` expects), so a shape mismatch fails loudly
instead of a generic mock silently returning another mock.
"""
import json
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

import app.agent as agent_module
from app.agent_langgraph import REFUSAL_MESSAGE, MAX_GUARDRAIL_RETRIES, ask_langgraph, build_graph


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction
    type: str = "function"


class FakeMessage:
    def __init__(self, content: str | None = None, tool_calls: list[FakeToolCall] | None = None):
        self.content = content
        self.tool_calls = tool_calls


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


def test_returns_final_answer_with_no_tool_calls():
    client = FakeOpenAIClient([_final("The average order value is R$120.")])

    result = ask_langgraph("What's the average order value?", client=client)

    assert result.answer == "The average order value is R$120."
    assert result.iterations_used == 1
    assert result.trace == []


def test_runs_a_tool_then_answers():
    client = FakeOpenAIClient(
        [
            _tool_call("calculator", {"expression": "2+2"}),
            _final("The answer is 4."),
        ]
    )

    result = ask_langgraph("what is 2+2?", client=client)

    assert result.answer == "The answer is 4."
    assert result.iterations_used == 2
    assert len(result.trace) == 1
    assert result.trace[0]["tool"] == "calculator"
    assert result.trace[0]["result"] == {"result": 4}


def test_unknown_tool_name_reports_error_and_continues():
    client = FakeOpenAIClient(
        [
            _tool_call("not_a_real_tool", {}),
            _final("ok, moving on"),
        ]
    )

    result = ask_langgraph("call something that doesn't exist", client=client)

    assert result.answer == "ok, moving on"
    assert result.trace[0]["result"] == {"error": "Unknown tool: not_a_real_tool"}


def test_tool_exception_routes_to_fallback_instead_of_crashing():
    # Wrong kwarg name -> run_calculator(**kwargs) raises TypeError, exercising
    # the call_tool -> fallback edge (current tools never raise on their own,
    # this is the graph-level safety net for a malformed call).
    client = FakeOpenAIClient([_tool_call("calculator", {"totally_wrong_kwarg": "1+1"})])

    result = ask_langgraph("trigger the fallback path", client=client)

    assert "unexpected error" in result.answer
    assert "totally_wrong_kwarg" in result.answer


def _fake_sql_query_respecting_guardrail(query: str) -> dict:
    # Stands in for the DB call in run_sql_query while still running the real
    # guardrail check, so this test exercises real guardrail behavior without
    # needing a live Postgres connection.
    from app.tools.sql_guard import check_query

    error = check_query(query)
    if error:
        return {"error": error}
    return {"columns": ["n"], "rows": [(1,)], "row_count": 1}


def test_guardrail_violation_is_fed_back_and_can_be_corrected(monkeypatch):
    monkeypatch.setitem(agent_module.TOOLS_BY_NAME, "sql_query", _fake_sql_query_respecting_guardrail)
    client = FakeOpenAIClient(
        [
            _tool_call("sql_query", {"query": "DELETE FROM orders"}, call_id="c1"),
            _tool_call("sql_query", {"query": "SELECT * FROM orders LIMIT 1"}, call_id="c2"),
            _final("Here's the order."),
        ]
    )

    result = ask_langgraph("show me an order", client=client)

    assert result.answer == "Here's the order."
    # The rejected query's own trace entry carries check_query's real message
    # (surfaced by run_sql_query's own internal guardrail, unchanged) -- the
    # second, corrected query is what let the loop reach a final answer.
    assert result.trace[0]["result"]["error"] == "Only SELECT statements (optionally starting with WITH) are allowed."
    assert len(result.trace) == 2
    assert result.trace[1]["result"]["row_count"] == 1


def test_guardrail_violation_gives_up_after_max_retries():
    responses = [_tool_call("sql_query", {"query": "DROP TABLE orders"}, call_id=f"c{i}") for i in range(10)]
    client = FakeOpenAIClient(responses)

    result = ask_langgraph("drop the table", client=client, max_iterations=20)

    assert result.answer == REFUSAL_MESSAGE
    # 1 initial attempt + MAX_GUARDRAIL_RETRIES retries, then give up.
    assert len(client.completions.calls) == MAX_GUARDRAIL_RETRIES + 1


def test_max_iterations_cutoff_refuses_instead_of_looping_forever():
    responses = [_tool_call("calculator", {"expression": "1+1"}, call_id=f"c{i}") for i in range(10)]
    client = FakeOpenAIClient(responses)

    result = ask_langgraph("keep going forever", client=client, max_iterations=3)

    assert result.answer == REFUSAL_MESSAGE
    assert result.iterations_used == 3


def test_checkpointing_carries_conversation_across_calls_with_same_thread_id():
    client = FakeOpenAIClient([_final("first answer"), _final("second answer, remembering context")])
    graph = build_graph(client=client)
    config = {"configurable": {"thread_id": "test-thread"}}

    def _initial_state(messages):
        return {
            "messages": messages,
            "guardrail_violation": None,
            "retries": 0,
            "tool_exception": None,
            "final_answer": None,
            "iterations_used": 0,
            "trace": [],
        }

    out1 = graph.invoke(
        _initial_state([SystemMessage(content="sys"), HumanMessage(content="q1")]), config=config
    )
    assert out1["final_answer"] == "first answer"

    out2 = graph.invoke(_initial_state([HumanMessage(content="q2 follow up")]), config=config)

    assert out2["final_answer"] == "second answer, remembering context"
    # system + q1 + ai(first answer) + q2 + ai(second answer) -- proves the
    # checkpoint actually carried turn 1's history into turn 2, not just that
    # turn 2 ran in isolation.
    assert len(out2["messages"]) == 5


def test_checkpointing_uses_a_fresh_thread_per_call_when_none_given():
    client = FakeOpenAIClient([_final("answer one"), _final("answer two")])

    result1 = ask_langgraph("question one", client=client)
    result2 = ask_langgraph("question two", client=client)

    assert result1.answer == "answer one"
    assert result2.answer == "answer two"
