"""
Second implementation of the same agent (see app.agent for the hand-rolled
loop) built on LangGraph's StateGraph -- same tools, same system prompt, same
SQL guardrails, same REFUSAL_MESSAGE, so the two are directly comparable via
the same eval set (eval/dataset.json). See README ("Why two implementations")
for the trade-off this is meant to demonstrate.

Graph shape:

    plan --(tool call)--> call_tool --(ok)--> validate_guardrail --(clean)--> plan
     |                        |                        |
     |(no tool call,          |(raises)                |(violation, retries
     | or out of iterations)  v                        | exhausted)
     v                     fallback  ------------------>+
   respond <----------------------------------------------------------------+
     |
     v
    END

`plan` is both the entry point and the loop-back target: every pass through
the graph either produces a final answer (no tool_calls -> respond) or a new
tool call to execute. Checkpointed with MemorySaver so a `thread_id` carries
conversation state across separate ask_langgraph() calls (see
tests/test_agent_langgraph.py for a multi-turn example) -- the eval runner
uses a fresh thread per question, since eval/dataset.json questions are
independent of each other.
"""
from __future__ import annotations

import json
import operator
import uuid
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import convert_to_openai_messages
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from openai import OpenAI

from app.agent import MAX_ITERATIONS, MODEL, REFUSAL_MESSAGE, TOOL_SCHEMAS, TOOLS_BY_NAME, AgentResult
from app.schema_doc import SYSTEM_PROMPT
from app.tools.sql_guard import check_query

# Independent from MAX_ITERATIONS (the overall step budget, same as the
# manual loop): this caps how many times validate_guardrail sends a rejected
# query back to plan before giving up in a controlled way, so a model stuck
# repeating the same disallowed query can't burn the whole iteration budget
# on guardrail retries alone.
MAX_GUARDRAIL_RETRIES = 3

_UNSUPPORTED_PREFIX = "__unsupported_"


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    guardrail_violation: str | None
    retries: int
    tool_exception: str | None
    final_answer: str | None
    iterations_used: int
    trace: Annotated[list[dict[str, Any]], operator.add]


def _execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name.startswith(_UNSUPPORTED_PREFIX):
        call_type = name.removeprefix(_UNSUPPORTED_PREFIX).removesuffix("__")
        return {"error": f"Unsupported tool call type: {call_type}"}
    tool_fn = TOOLS_BY_NAME.get(name)
    if tool_fn is None:
        return {"error": f"Unknown tool: {name}"}
    return tool_fn(**args)


def _plan(state: AgentState, *, client: OpenAI, max_iterations: int) -> dict[str, Any]:
    openai_messages = convert_to_openai_messages(state["messages"])
    response = client.chat.completions.create(
        model=MODEL,
        messages=openai_messages,  # type: ignore[arg-type]
        tools=TOOL_SCHEMAS,
        temperature=0,
    )
    message = response.choices[0].message
    iterations_used = state["iterations_used"] + 1

    if not message.tool_calls:
        return {
            "messages": [AIMessage(content=message.content or "")],
            "final_answer": message.content or "",
            "iterations_used": iterations_used,
        }

    if iterations_used >= max_iterations:
        # Budget exhausted on a turn that still wanted to call a tool --
        # refuse rather than let the graph loop forever (same "refuse
        # instead of guess" cutoff the manual loop applies).
        return {
            "messages": [AIMessage(content=message.content or "")],
            "final_answer": REFUSAL_MESSAGE,
            "iterations_used": iterations_used,
        }

    tool_calls = []
    for tc in message.tool_calls:
        if tc.type != "function":
            tool_calls.append({"name": f"{_UNSUPPORTED_PREFIX}{tc.type}__", "args": {}, "id": tc.id, "type": "tool_call"})
            continue
        try:
            args = json.loads(tc.function.arguments)
        except ValueError:
            args = {}
        tool_calls.append({"name": tc.function.name, "args": args, "id": tc.id, "type": "tool_call"})

    return {
        "messages": [AIMessage(content=message.content or "", tool_calls=tool_calls)],
        "iterations_used": iterations_used,
    }


def _call_tool(state: AgentState) -> dict[str, Any]:
    last = state["messages"][-1]
    assert isinstance(last, AIMessage)

    try:
        tool_messages: list[BaseMessage] = []
        trace_entries: list[dict[str, Any]] = []
        for tc in last.tool_calls:
            result = _execute_tool(tc["name"], tc["args"])
            trace_entries.append(
                {"iteration": state["iterations_used"], "tool": tc["name"], "arguments": tc["args"], "result": result}
            )
            tool_messages.append(
                ToolMessage(content=_to_json(result), tool_call_id=tc["id"], name=tc["name"])
            )
    except Exception as e:  # pragma: no cover -- current tools never raise, this is a graph-level safety net
        return {"tool_exception": str(e)}

    return {"messages": tool_messages, "trace": trace_entries, "tool_exception": None}


def _validate_guardrail(state: AgentState) -> dict[str, Any]:
    last_ai = next(m for m in reversed(state["messages"]) if isinstance(m, AIMessage))
    violations = []
    for tc in last_ai.tool_calls:
        if tc["name"] != "sql_query":
            continue
        query = tc["args"].get("query", "")
        error = check_query(query)
        if error:
            violations.append(error)

    if violations:
        reason = "; ".join(violations)
        return {
            "guardrail_violation": reason,
            "retries": state["retries"] + 1,
            "messages": [HumanMessage(content=f"Guardrail rejected the last query: {reason}. Try a corrected query.")],
        }

    return {"guardrail_violation": None}


def _fallback(state: AgentState) -> dict[str, Any]:
    return {
        "final_answer": (
            "I ran into an unexpected error executing a tool and I'm stopping "
            f"here rather than guess: {state['tool_exception']}"
        )
    }


def _respond(state: AgentState) -> dict[str, Any]:
    answer = state["final_answer"]
    if answer is None:
        answer = REFUSAL_MESSAGE
    return {"final_answer": answer}


def _route_after_plan(state: AgentState) -> str:
    return "respond" if state.get("final_answer") is not None else "call_tool"


def _route_after_call_tool(state: AgentState) -> str:
    return "fallback" if state.get("tool_exception") else "validate_guardrail"


def _route_after_validate_guardrail(state: AgentState) -> str:
    if state.get("guardrail_violation") and state["retries"] > MAX_GUARDRAIL_RETRIES:
        return "give_up"
    return "plan"


def _give_up(state: AgentState) -> dict[str, Any]:
    return {"final_answer": REFUSAL_MESSAGE}


def _to_json(value: Any) -> str:
    return json.dumps(value, default=str)


def build_graph(*, client: OpenAI, max_iterations: int = MAX_ITERATIONS) -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("plan", lambda state: _plan(state, client=client, max_iterations=max_iterations))
    graph.add_node("call_tool", _call_tool)
    graph.add_node("validate_guardrail", _validate_guardrail)
    graph.add_node("fallback", _fallback)
    graph.add_node("give_up", _give_up)
    graph.add_node("respond", _respond)

    graph.set_entry_point("plan")
    graph.add_conditional_edges("plan", _route_after_plan, {"respond": "respond", "call_tool": "call_tool"})
    graph.add_conditional_edges("call_tool", _route_after_call_tool, {"fallback": "fallback", "validate_guardrail": "validate_guardrail"})
    graph.add_conditional_edges(
        "validate_guardrail", _route_after_validate_guardrail, {"plan": "plan", "give_up": "give_up"}
    )
    graph.add_edge("fallback", "respond")
    graph.add_edge("give_up", "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=MemorySaver())


def ask_langgraph(
    question: str,
    client: OpenAI | None = None,
    max_iterations: int = MAX_ITERATIONS,
    thread_id: str | None = None,
) -> AgentResult:
    client = client or OpenAI()
    app = build_graph(client=client, max_iterations=max_iterations)

    initial_state: AgentState = {
        "messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)],
        "guardrail_violation": None,
        "retries": 0,
        "tool_exception": None,
        "final_answer": None,
        "iterations_used": 0,
        "trace": [],
    }

    config: RunnableConfig = {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}, "recursion_limit": 50}
    final_state = app.invoke(initial_state, config=config)

    return AgentResult(
        answer=final_state["final_answer"] or REFUSAL_MESSAGE,
        trace=final_state["trace"],
        iterations_used=final_state["iterations_used"],
    )
