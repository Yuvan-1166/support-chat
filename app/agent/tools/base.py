"""Shared helpers for AGENT-mode tools.

Tools return JSON strings (LangChain tool outputs are strings).  Confirmation
gating works by returning a sentinel payload that the AGENT graph detects after
ToolNode runs — the tool itself performs NO side effect until ``ctx.confirmed``
is set on a follow-up request.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from app.agent.guardrails import confirmation_prompt, requires_confirmation
from app.agent.state import AgentContext
from app.crm.client import CRMError

# Sentinel key embedded in a tool result that means "stop and ask the user".
CONFIRM_MARKER = "__requires_confirmation__"


def ok(data: Any) -> str:
    return json.dumps({"success": True, "data": data}, default=str)


def err(message: str, **extra: Any) -> str:
    return json.dumps({"success": False, "error": message, **extra}, default=str)


def pending(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Return the confirmation sentinel for a gated action (no side effect)."""
    return json.dumps(
        {
            CONFIRM_MARKER: True,
            "tool": tool_name,
            "tool_input": tool_input,
            "prompt": confirmation_prompt(tool_name, tool_input),
        },
        default=str,
    )


def gate(ctx: AgentContext, tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """If *tool_name* needs confirmation and none was given, return the sentinel.

    Returns ``None`` when the tool is cleared to run.
    """
    if requires_confirmation(tool_name) and not ctx.confirmed:
        return pending(tool_name, tool_input)
    return None


def call(fn: Callable[[], Any]) -> str:
    """Run a CRM call, normalising success/errors into a JSON tool result."""
    try:
        return ok(fn())
    except CRMError as exc:
        return err(exc.message, status_code=exc.status_code, body=exc.body)
    except Exception as exc:  # pragma: no cover - defensive
        return err(str(exc))
