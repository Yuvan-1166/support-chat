"""AGENT-mode tools: tasks, Google Calendar sync, and Google Meet links."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool, tool

from app.agent.state import AgentContext
from app.agent.tools.base import call, gate
from app.crm import endpoints as ep
from app.crm.client import CRMClient


def build_task_tools(crm: CRMClient, ctx: AgentContext) -> list[StructuredTool]:
    @tool
    def create_task(
        title: str,
        due_date: str,
        description: Optional[str] = None,
        task_type: str = "FOLLOW_UP",
        priority: str = "MEDIUM",
        due_time: Optional[str] = None,
        contact_id: Optional[int] = None,
        generate_meet_link: bool = False,
    ) -> str:
        """Create a task. `due_date` is required (YYYY-MM-DD). Optionally link a
        contact and auto-generate a Google Meet link for MEETING/DEMO tasks.
        task_type: FOLLOW_UP|MEETING|DEMO|CALL. priority: LOW|MEDIUM|HIGH."""
        return call(
            lambda: crm.post(
                ep.TASKS,
                json={
                    "title": title,
                    "due_date": due_date,
                    "description": description,
                    "task_type": task_type,
                    "priority": priority,
                    "due_time": due_time,
                    "contact_id": contact_id,
                    "generate_meet_link": generate_meet_link,
                },
            )
        )

    @tool
    def update_task(task_id: int, fields: dict) -> str:
        """Update a task's fields. `fields` is a dict of fields to change."""
        return call(lambda: crm.put(ep.TASK.format(task_id=task_id), json=fields))

    @tool
    def get_task(task_id: int) -> str:
        """Fetch a single task's details by id."""
        return call(lambda: crm.get(ep.TASK.format(task_id=task_id)))

    @tool
    def list_tasks(scope: str = "today", limit: int = 20) -> str:
        """List tasks by scope: 'today', 'week', 'overdue', or 'upcoming'."""
        path = {
            "today": ep.TASKS_TODAY,
            "week": ep.TASKS_WEEK,
            "overdue": ep.TASKS_OVERDUE,
            "upcoming": ep.TASKS_UPCOMING,
        }.get(scope, ep.TASKS_TODAY)
        params = {"limit": limit} if scope == "upcoming" else None
        return call(lambda: crm.get(path, params=params))

    @tool
    def resolve_task(task_id: int, resolution: str, rating: Optional[int] = None, feedback: Optional[str] = None) -> str:
        """Close out an overdue task. resolution: COMPLETED|NOT_CONNECTED|BAD_TIMING."""
        return call(
            lambda: crm.post(
                ep.TASK_RESOLVE.format(task_id=task_id),
                json={"resolution": resolution, "rating": rating, "feedback": feedback},
            )
        )

    @tool
    def generate_meet_link(task_id: int) -> str:
        """Generate a Google Meet link for a MEETING/DEMO task (Calendar must be connected)."""
        return call(lambda: crm.post(ep.TASK_MEET_LINK.format(task_id=task_id)))

    @tool
    def sync_task_to_calendar(task_id: int) -> str:
        """Push a single task to the employee's connected Google Calendar."""
        return call(lambda: crm.post(ep.CALENDAR_SYNC_TASK.format(task_id=task_id)))

    @tool
    def calendar_sync_status() -> str:
        """Check whether the employee's Google Calendar is connected."""
        return call(lambda: crm.get(ep.CALENDAR_SYNC_STATUS))

    @tool
    def delete_task(task_id: int) -> str:
        """Delete a task. Confirmation-gated."""
        pend = gate(ctx, "delete_task", {"task_id": task_id})
        if pend:
            return pend
        return call(lambda: crm.delete(ep.TASK.format(task_id=task_id)))

    return [
        create_task,
        update_task,
        get_task,
        list_tasks,
        resolve_task,
        generate_meet_link,
        sync_task_to_calendar,
        calendar_sync_status,
        delete_task,
    ]
