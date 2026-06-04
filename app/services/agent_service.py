"""Agent service — LangGraph-based multi-step reasoning loop.

This implements a stateful agent that can reason about user requests,
decide which tools to use, execute them, and adjust based on results.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.agent_tools import AgentToolkit, ToolResult
from app.services.session_store import Session, SessionStoreBase
from app.services.translator import QueryTranslator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# State and Message Models
# ─────────────────────────────────────────────────────────────────

class AgentStepInfo(BaseModel):
    """Information about a single agent step."""

    step: int
    node: str  # 'think', 'execute_tool', 'loop_or_end'
    thought: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    tool_result: Optional[dict[str, Any]] = None
    action: str = ""  # Free-form description of what happened


class AgentResponse(BaseModel):
    """Response from agent.run_agent()."""

    role: str = "assistant"
    content: str
    agent_reasoning: list[AgentStepInfo] = Field(default_factory=list)
    final_tool_results: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


class AgentState(BaseModel):
    """LangGraph state for the agent loop."""

    """LangGraph state for the agent loop."""
    model_config = {"arbitrary_types_allowed": True}

    # Input
    user_message: str
    session: Session

    # Reasoning and planning
    reasoning: str = ""
    current_step: int = 0
    max_steps: int = 10

    # Tool usage
    selected_tool: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    tool_results: list[dict[str, Any]] = Field(default_factory=list)

    # Execution control
    should_continue: bool = True
    next_node: Literal["think", "execute_tool", "loop_or_end"] = "think"

    # Final output
    final_response: str = ""
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────
# Agent Service
# ─────────────────────────────────────────────────────────────────

class AgentService:
    """Multi-step agent using LangGraph for orchestration."""

    def __init__(
        self,
        session_store: SessionStoreBase,
        translator: QueryTranslator,
    ) -> None:
        self.session_store = session_store
        self.translator = translator
        self.toolkit = AgentToolkit(session_store, translator)

        # Initialize LLM for agent reasoning
        self.llm = ChatGroq(
                model=get_settings().GROQ_MODEL,
                api_key=get_settings().GROQ_API_KEY,
            temperature=0.2,
        )

        # Build the state graph
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the LangGraph state machine."""
        graph = StateGraph(AgentState)

        # Add nodes
        graph.add_node("think", self._node_think)
        graph.add_node("execute_tool", self._node_execute_tool)
        graph.add_node("loop_or_end", self._node_loop_or_end)

        # Set entry point
        graph.add_edge(START, "think")

        # Conditional routing after each node
        graph.add_conditional_edges(
            "think",
            lambda state: "execute_tool" if state.selected_tool else "loop_or_end",
        )
        graph.add_conditional_edges(
            "execute_tool",
            lambda state: "think" if state.should_continue else "loop_or_end",
        )
        graph.add_edge("loop_or_end", END)

        return graph.compile()

    def _node_think(self, state: AgentState) -> AgentState:
        """LLM reasoning node: decide what to do next."""
        state.current_step += 1

        # Build context for the LLM
        available_tools = self.toolkit.get_tools()
        tool_descriptions = "\n".join([
            f"- {name}: {fn.__doc__.split(chr(10))[0]}" if fn.__doc__ else f"- {name}"
            for name, fn in available_tools.items()
        ])

        recent_history = state.session.messages[-5:]
        history_str = "\n".join([
            f"{m['role']}: {m['content']}"
            for m in recent_history
        ])

        prompt = f"""You are a helpful AI agent that helps users with data queries and CRM operations.

User's current request: {state.user_message}

Available tools:
{tool_descriptions}

Session info:
- Query type: {state.session.query_type}
- Has DB connection: {state.session.has_db_connection}
- Schema tables: {[t.name for t in state.session.schema_context]}

Recent conversation:
{history_str if history_str else "(no history yet)"}

Previous steps taken: {len(state.tool_results)}

Based on the user's request, decide:
1. Do you understand what the user wants?
2. Which tool(s) would help you fulfill the request?
3. What inputs would you provide to that tool?

Respond in JSON format:
{{
    "thought": "Your reasoning about what to do",
    "selected_tool": "tool_name or null if done",
    "tool_input": {{"param": "value"}},
    "is_complete": false
}}

Only include the JSON in your response."""

        try:
            response = self.llm.invoke(prompt)
            response_text = response.content

            # Parse JSON
            try:
                parsed = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from the response
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(response_text[start:end])
                else:
                    raise ValueError("Could not parse LLM response as JSON")

            state.reasoning = parsed.get("thought", "")
            state.selected_tool = parsed.get("selected_tool")
            state.tool_input = parsed.get("tool_input", {})

            logger.debug(
                f"Agent step {state.current_step}: selected_tool={state.selected_tool}, "
                f"reasoning={state.reasoning[:80]}"
            )

        except Exception as exc:
            logger.exception("LLM reasoning failed")
            state.error = f"Reasoning error: {exc}"
            state.should_continue = False
            state.selected_tool = None

        return state

    def _node_execute_tool(self, state: AgentState) -> AgentState:
        """Execute the selected tool."""
        if not state.selected_tool:
            return state

        logger.debug(
            f"Executing tool: {state.selected_tool} with input {state.tool_input}"
        )

        result = self.toolkit.call_tool(state.session, state.selected_tool, state.tool_input or {})

        # Convert result to dict for storage
        result_dict = {
            "tool": state.selected_tool,
            "success": result.success,
            "data": result.data,
            "error": result.error,
        }
        state.tool_results.append(result_dict)

        # Decide if we should continue looping
        if not result.success:
            # Tool failed; might want to try something else or give up
            if state.current_step >= state.max_steps:
                state.should_continue = False
            # else: stay in loop to try a different tool
        else:
            # Tool succeeded; check if we've done enough
            if state.current_step >= state.max_steps:
                state.should_continue = False
            # else: loop back to think about next step

        return state

    def _node_loop_or_end(self, state: AgentState) -> AgentState:
        """Final node: either loop or end the agent."""
        # Build a final response based on what we've done
        if state.error:
            state.final_response = f"Error during agent execution: {state.error}"
        elif not state.tool_results:
            state.final_response = state.reasoning or "I didn't take any actions."
        else:
            # Summarize what we did
            summary_lines = [
                f"I completed {len(state.tool_results)} step(s):"
            ]
            for i, result in enumerate(state.tool_results, 1):
                tool = result["tool"]
                success = result["success"]
                status = "✓" if success else "✗"
                summary_lines.append(f"  {status} {tool}: {result.get('error', 'success')}")

            state.final_response = "\n".join(summary_lines)

        return state

    def run_agent(
        self,
        session: Session,
        user_message: str,
        max_steps: int = 10,
    ) -> AgentResponse:
        """Run the agent loop for a given user message.
        
        Args:
            session: The current session
            user_message: The user's request
            max_steps: Maximum steps to take before ending
        
        Returns:
            AgentResponse with reasoning and results
        """
        # Initialize state
        initial_state = AgentState(
            user_message=user_message,
            session=session,
            max_steps=max_steps,
        )

        try:
            # Run the graph
            final_state = self._graph.invoke(initial_state)

            # Convert to AgentResponse
            reasoning_steps = []
            for i, result in enumerate(final_state.tool_results, 1):
                step = AgentStepInfo(
                    step=i,
                    node="execute_tool",
                    tool_name=result["tool"],
                    tool_result=result.get("data") or result.get("error"),
                    action=f"Executed {result['tool']}: {result['error'] if not result['success'] else 'success'}",
                )
                reasoning_steps.append(step)

            response = AgentResponse(
                content=final_state.final_response,
                agent_reasoning=reasoning_steps,
                final_tool_results=final_state.tool_results,
                error=final_state.error,
            )
            return response

        except Exception as exc:
            logger.exception("Agent execution failed")
            return AgentResponse(
                content="Agent encountered an error during execution.",
                error=str(exc),
            )


# ─────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────

_agent_service: Optional[AgentService] = None


def get_agent_service(
    session_store: SessionStoreBase,
    translator: QueryTranslator,
) -> AgentService:
    """Get or create the global agent service."""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService(session_store, translator)
    return _agent_service
