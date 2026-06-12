"""AGENT mode — ReAct loop that automates CRM features via tools.

LangGraph ReAct: ``agent`` (LLM with bound tools) ⇄ ``tools`` (ToolNode), looping
until the model stops calling tools or the step cap is hit.  Destructive/outbound
tools are confirmation-gated: when unconfirmed they return a sentinel instead of
acting, and the graph halts so the API can ask the user to confirm.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app.agent.guardrails import confirmation_prompt
from app.agent.state import AgentContext, ModeResult, PendingAction
from app.agent.tools import build_agent_tools
from app.agent.tools.base import CONFIRM_MARKER
from app.core.config import get_settings
from app.crm.client import CRMClient

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an autonomous assistant operating inside a CRM as the signed-in "
    "employee (company_id={company_id}, role={role}). Fulfil the user's request "
    "by calling the available tools. Guidelines:\n"
    "- Break the request into tool calls; inspect results before the next step.\n"
    "- For automations, call automation_metadata first to learn valid trigger/action names.\n"
    "- Some tools (sending email/outreach, closing deals, creating automations, "
    "deleting) require user confirmation — if a tool reports it needs confirmation, "
    "STOP and report the pending action; do not retry it.\n"
    "- When the task is complete, give a short natural-language summary of what you did.\n"
    "- Never fabricate IDs; look them up with search/list tools first."
)


class GraphState(TypedDict):
    messages: Annotated[list, add_messages]
    steps: int


def _find_pending(messages: list) -> Optional[dict]:
    """Return the parsed confirmation sentinel from the latest tool batch, if any."""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get(CONFIRM_MARKER):
                return data
        elif isinstance(msg, AIMessage):
            # Stop scanning once we pass the most recent tool-call batch.
            if not getattr(msg, "tool_calls", None):
                continue
            break
    return None


def _build_graph(ctx: AgentContext, tools: list):
    settings = get_settings()
    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.2,
    ).bind_tools(tools)
    tool_node = ToolNode(tools)

    def call_model(state: GraphState) -> GraphState:
        response = llm.invoke(state["messages"])
        return {"messages": [response], "steps": state["steps"] + 1}

    def route_after_model(state: GraphState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None) and state["steps"] < ctx.max_steps:
            return "tools"
        return END

    def route_after_tools(state: GraphState) -> str:
        # Halt immediately if a tool asked for confirmation.
        if _find_pending(state["messages"]):
            return END
        return "agent"

    g = StateGraph(GraphState)
    g.add_node("agent", call_model)
    g.add_node("tools", tool_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_model, {"tools": "tools", END: END})
    g.add_conditional_edges("tools", route_after_tools, {"agent": "agent", END: END})
    return g.compile()


def _collect_reasoning(messages: list) -> tuple[list[dict], list[dict]]:
    """Extract (reasoning_steps, tool_results) from the final message list."""
    reasoning: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    step = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                step += 1
                reasoning.append(
                    {
                        "step": step,
                        "thought": msg.content or "",
                        "tool_name": tc.get("name"),
                        "tool_input": tc.get("args"),
                    }
                )
        elif isinstance(msg, ToolMessage):
            try:
                parsed = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                parsed = msg.content
            tool_results.append({"tool_call_id": msg.tool_call_id, "result": parsed})
    return reasoning, tool_results


def run_agent(ctx: AgentContext, message: str) -> ModeResult:
    """Run the ReAct agent for one user turn."""
    crm = CRMClient(jwt=ctx.request.raw_jwt)
    try:
        tools = build_agent_tools(ctx, crm)
        system = _SYSTEM.format(
            company_id=ctx.request.company_id, role=ctx.request.role or "EMPLOYEE"
        )
        init = {
            "messages": [SystemMessage(content=system), HumanMessage(content=message)],
            "steps": 0,
        }
        try:
            final = _build_graph(ctx, tools).invoke(init)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("AGENT mode failed")
            return ModeResult(mode="agent", content="The agent hit an error.", error=str(exc))

        messages = final["messages"]
        reasoning, tool_results = _collect_reasoning(messages)

        pending = _find_pending(messages)
        if pending:
            action = PendingAction(
                tool=pending.get("tool", "?"),
                tool_input=pending.get("tool_input", {}),
                prompt=pending.get("prompt")
                or confirmation_prompt(pending.get("tool", "?"), pending.get("tool_input")),
            )
            return ModeResult(
                mode="agent",
                content=action.prompt,
                requires_confirmation=True,
                pending_action=action,
                agent_reasoning=reasoning,
                tool_results=tool_results,
            )

        # Final assistant text is the content of the last AIMessage without tool calls.
        final_text = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                final_text = msg.content or ""
                break

        return ModeResult(
            mode="agent",
            content=final_text or "Done.",
            agent_reasoning=reasoning,
            tool_results=tool_results,
        )
    finally:
        crm.close()
