"""Offline unit tests for shared/llm_agent.py's generic tool-calling loop.

Uses a minimal fake client (not LangChain's own fakes, which ignore the
bind()/bind_tools() chain) so we can both script responses and record what
context each invoke() call actually received.
"""
from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.llm_agent import run_tool_calling_agent


class _FakeBound:
    def __init__(self, parent):
        self.parent = parent

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        self.parent.invocations.append(list(messages))
        return self.parent.responses.pop(0)


class FakeAgentClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.invocations = []

    def bind_tools(self, tools, tool_choice=None):
        return _FakeBound(self)


TOOLS = [{"type": "function", "function": {"name": "search", "parameters": {"type": "object", "properties": {}}}}]


def test_converges_immediately_with_no_tool_calls():
    client = FakeAgentClient([AIMessage(content="direct answer")])
    result = run_tool_calling_agent(
        client, "m", [SystemMessage(content="s"), HumanMessage(content="q")], TOOLS, run_tool=lambda n, a: "x"
    )
    assert result.converged
    assert result.content == "direct answer"
    assert result.agent_steps == []


def test_tool_call_then_final_answer():
    client = FakeAgentClient([
        AIMessage(content="", tool_calls=[{"name": "search", "args": {"query": "revenue"}, "id": "call_1", "type": "tool_call"}]),
        AIMessage(content="final answer using retrieved data"),
    ])
    calls = []

    def run_tool(name, args):
        calls.append((name, args))
        return "retrieved: $100"

    result = run_tool_calling_agent(
        client, "m", [SystemMessage(content="s"), HumanMessage(content="q")], TOOLS, run_tool=run_tool
    )
    assert result.converged
    assert result.content == "final answer using retrieved data"
    assert calls == [("search", {"query": "revenue"})]
    assert result.agent_steps == [{"tool": "search", "input": {"query": "revenue"}, "output": "retrieved: $100", "error": False}]


def test_never_converging_hits_safety_cap():
    # Always returns a tool call — should stop at max_total_tool_calls, not loop forever.
    infinite_tool_call = AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "call_x", "type": "tool_call"}])
    client = FakeAgentClient([infinite_tool_call] * 50)
    result = run_tool_calling_agent(
        client, "m", [SystemMessage(content="s")], TOOLS, run_tool=lambda n, a: "data",
        max_total_tool_calls=4, max_iterations=20,
    )
    assert not result.converged
    assert result.content is None
    assert len(result.agent_steps) == 4  # stopped exactly at the cap, not before or after


def test_error_streak_triggers_escalation_message():
    calls_seen = {"count": 0}

    def run_tool(name, args):
        calls_seen["count"] += 1
        return "ERROR: bad code"

    def is_error(name, result):
        return result.startswith("ERROR")

    client = FakeAgentClient([
        AIMessage(content="", tool_calls=[{"name": "run_python", "args": {}, "id": f"c{i}", "type": "tool_call"}])
        for i in range(3)
    ] + [AIMessage(content="gave up, best-effort answer")])

    result = run_tool_calling_agent(
        client, "m", [SystemMessage(content="s")], TOOLS, run_tool=run_tool,
        is_error=is_error, max_error_retries=3,
    )
    assert result.converged
    assert calls_seen["count"] == 3
    # 4th invoke's context should include the escalation HumanMessage appended after the 3rd error.
    last_context = client.invocations[-1]
    assert any(isinstance(m, HumanMessage) and "failed too many times" in m.content for m in last_context)


def test_context_trimmed_by_whole_turns_not_mid_turn():
    # 5 tool-call turns then a final answer. With max_context_turns=2, the
    # last invoke's context must contain the fixed opening plus at most the
    # last 2 turns — and never split an assistant message from its tool reply.
    responses = [
        AIMessage(content="", tool_calls=[{"name": "search", "args": {"i": i}, "id": f"c{i}", "type": "tool_call"}])
        for i in range(5)
    ] + [AIMessage(content="done")]
    client = FakeAgentClient(responses)
    opening = [SystemMessage(content="SYS")]
    result = run_tool_calling_agent(
        client, "m", opening, TOOLS, run_tool=lambda n, a: "ok", max_context_turns=2, max_total_tool_calls=20,
    )
    assert result.converged
    last_context = client.invocations[-1]
    assert last_context[0].content == "SYS"  # opening always present
    # Only turns for i=3 and i=4 (the last 2) should remain — i=0,1,2 trimmed.
    ai_msgs_with_tool_calls = [m for m in last_context if isinstance(m, AIMessage) and m.tool_calls]
    seen_indices = {tc["args"]["i"] for m in ai_msgs_with_tool_calls for tc in m.tool_calls}
    assert seen_indices == {3, 4}
