"""AGENT-mode tool registry.

``build_agent_tools(ctx)`` constructs a per-request CRM client (authenticated
with the forwarded employee JWT) and returns the full LangChain tool list for
the AGENT graph to bind.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.agent.state import AgentContext
from app.agent.tools.automations import build_automation_tools
from app.agent.tools.contacts import build_contact_tools
from app.agent.tools.email import build_email_tools
from app.agent.tools.tasks import build_task_tools
from app.crm.client import CRMClient

__all__ = ["build_agent_tools"]


def build_agent_tools(ctx: AgentContext, crm: CRMClient) -> list[StructuredTool]:
    """Build all AGENT-mode tools bound to *ctx*'s identity and confirm flag.

    The *crm* client is owned by the caller (so it can be closed after the run).
    """
    tools: list[StructuredTool] = []
    tools += build_task_tools(crm, ctx)
    tools += build_email_tools(crm, ctx)
    tools += build_automation_tools(crm, ctx)
    tools += build_contact_tools(crm, ctx)
    return tools
