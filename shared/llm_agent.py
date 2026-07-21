"""One generic LangChain tool-calling agent loop, shared by all 6 apps.

Previously this loop (iteration caps, per-turn tool-call caps, malformed
tool-call handling, turn-grouped context trimming) was hand-rolled and
copy-pasted separately inside apps 4, 5, and 6. Centralizing it here means
every app — including 1, 2, 3, which previously did a single direct
retrieve-then-generate call with no agent — gets the same battle-tested
convergence/safety behavior instead of six divergent implementations.

The turn-grouping (not raw message-count) is deliberate: the chat API
requires an assistant message that issues tool_calls to stay adjacent to its
tool responses, so context gets trimmed by whole turns, never mid-turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from openai import BadRequestError


def _flatten(turns: List[List[BaseMessage]]) -> List[BaseMessage]:
    return [m for turn in turns for m in turn]


@dataclass
class AgentResult:
    content: Optional[str]  # final assistant text; None if it never converged
    agent_steps: List[dict] = field(default_factory=list)
    converged: bool = False
    # Full (untrimmed) conversation including the final response, so a caller
    # that needs to repair a malformed JSON answer can re-prompt with the
    # actual tool-call trace still in context, instead of starting cold.
    messages: List[BaseMessage] = field(default_factory=list)


def run_tool_calling_agent(
    client: Any,
    model: str,
    initial_messages: List[BaseMessage],
    tools: List[dict],
    run_tool: Callable[[str, dict], str],
    max_iterations: int = 12,
    max_tool_calls_per_turn: int = 3,
    max_total_tool_calls: int = 12,
    max_context_turns: Optional[int] = None,
    is_error: Optional[Callable[[str, str], bool]] = None,
    max_error_retries: int = 3,
    escalation_message: str = (
        "That approach failed too many times. Provide the best answer you can "
        "from what you've already gathered."
    ),
    stop_when: Optional[Callable[[], bool]] = None,
) -> AgentResult:
    """Run a tool-calling agent loop until the model answers without calling
    a tool, or a safety cap is hit.

    `initial_messages` (system/history/user context) is always included in
    full and never trimmed. Everything after that is grouped into turns —
    [AIMessage-with-tool-calls, ToolMessage, ToolMessage, ...] — and only
    whole turns are dropped from context when `max_context_turns` is set.

    `stop_when`, if given, is checked after each turn's tool calls run — lets
    a caller whose tools accumulate results via a side-effect (e.g. a
    write_section tool filling a shared dict) end the loop early once it has
    everything it needs, instead of waiting for the model to stop calling
    tools on its own.
    """
    bound = client.bind_tools(tools, tool_choice="auto") if tools else client
    bound = bound.bind(model=model, temperature=0)

    opening = list(initial_messages)
    turns: List[List[BaseMessage]] = []
    agent_steps: List[dict] = []
    total_tool_calls = 0
    error_streak = 0

    for _ in range(max_iterations):
        if total_tool_calls >= max_total_tool_calls:
            break

        recent_turns = turns if max_context_turns is None else turns[-max_context_turns:]
        context = opening + _flatten(recent_turns)

        try:
            response = bound.invoke(context)
        except BadRequestError:
            # Model generated a pathological tool call — stop, answer from what we have.
            break

        tool_calls = (response.tool_calls or [])[:max_tool_calls_per_turn]
        if not tool_calls:
            full_history = opening + _flatten(turns) + [response]
            return AgentResult(content=response.content or "", agent_steps=agent_steps, converged=True, messages=full_history)

        current_turn: List[BaseMessage] = [response]
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args") or {}
            try:
                result = run_tool(name, args)
            except Exception as e:
                result = f"ERROR: {e}"
            total_tool_calls += 1

            errored = bool(is_error and is_error(name, result))
            error_streak = error_streak + 1 if errored else 0

            agent_steps.append({"tool": name, "input": args, "output": result[:400], "error": errored})
            current_turn.append(ToolMessage(content=result, tool_call_id=tc["id"]))

            if errored and error_streak >= max_error_retries:
                current_turn.append(HumanMessage(content=escalation_message))

        turns.append(current_turn)

        if stop_when and stop_when():
            break

    full_history = opening + _flatten(turns)
    return AgentResult(content=None, agent_steps=agent_steps, converged=False, messages=full_history)
