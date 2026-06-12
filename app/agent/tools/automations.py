"""AGENT-mode tools: automation workflows (triggers, conditions, actions)."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool, tool

from app.agent.state import AgentContext
from app.agent.tools.base import call, gate
from app.crm import endpoints as ep
from app.crm.client import CRMClient


def build_automation_tools(crm: CRMClient, ctx: AgentContext) -> list[StructuredTool]:
    @tool
    def automation_metadata() -> str:
        """Get the available automation triggers, actions, and operators.
        Call this BEFORE creating an automation to learn valid trigger/action names."""
        return call(lambda: crm.get(ep.AUTOMATION_METADATA))

    @tool
    def list_automations(active_only: bool = False, limit: int = 50, offset: int = 0) -> str:
        """List the company's automation workflows."""
        params = {"limit": limit, "offset": offset}
        if active_only:
            params["activeOnly"] = "true"
        return call(lambda: crm.get(ep.AUTOMATIONS, params=params))

    @tool
    def get_automation(automation_id: int) -> str:
        """Fetch a single automation's configuration by id."""
        return call(lambda: crm.get(ep.AUTOMATION.format(automation_id=automation_id)))

    @tool
    def create_automation(name: str, trigger: dict, actions: list[dict], conditions: Optional[list[dict]] = None) -> str:
        """Create an automation workflow. `trigger` and `actions` must use names from
        automation_metadata. Confirmation-gated."""
        payload = {"name": name, "trigger": trigger, "actions": actions, "conditions": conditions or []}
        pend = gate(ctx, "create_automation", payload)
        if pend:
            return pend
        return call(lambda: crm.post(ep.AUTOMATIONS, json=payload))

    @tool
    def toggle_automation(automation_id: int, active: bool) -> str:
        """Enable or disable an automation workflow."""
        return call(lambda: crm.patch(ep.AUTOMATION_TOGGLE.format(automation_id=automation_id), json={"active": active}))

    @tool
    def automation_logs(automation_id: Optional[int] = None, limit: int = 25, status: Optional[str] = None) -> str:
        """Get automation execution logs — company-wide, or for a single automation."""
        if automation_id is not None:
            return call(
                lambda: crm.get(
                    ep.AUTOMATION_OWN_LOGS.format(automation_id=automation_id),
                    params={"limit": limit, "status": status},
                )
            )
        return call(lambda: crm.get(ep.AUTOMATION_LOGS, params={"limit": limit, "status": status}))

    return [
        automation_metadata,
        list_automations,
        get_automation,
        create_automation,
        toggle_automation,
        automation_logs,
    ]
