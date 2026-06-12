"""Shared types for the three-mode agent: execution context + uniform result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.request_context import RequestContext
from app.services.session_store import Session
from app.services.translator import QueryTranslator


@dataclass
class AgentContext:
    """Everything a mode graph needs to handle one chat turn.

    Threaded into the graphs and tool factory so nothing reaches for globals.
    """

    session: Session
    request: RequestContext
    translator: QueryTranslator
    # Set by the caller when the user has confirmed a previously-gated action.
    confirmed: bool = False
    max_steps: int = 10


@dataclass
class PendingAction:
    """A confirmation-gated action the agent wants to take, awaiting approval."""

    tool: str
    tool_input: dict[str, Any]
    prompt: str


@dataclass
class ModeResult:
    """Uniform result returned by every mode graph to the router/API layer."""

    mode: str
    content: str
    # VISUALIZE
    executed_query: Optional[str] = None
    query_result: Optional[Any] = None
    visualization: Optional[dict[str, Any]] = None
    # AGENT
    agent_reasoning: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    requires_confirmation: bool = False
    pending_action: Optional[PendingAction] = None
    # Shared
    sources: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
