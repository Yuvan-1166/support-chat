"""VISUALIZE mode — read-only insight queries → rows + chart spec.

Graph: ``generate`` (LLM emits SQL + chart spec) → ``validate`` (read-only +
tenant scoping) → ``execute`` (SQLAdapter, row-capped).  The service executes
the query (tenant-scoped) and returns both the rows and a visualization spec
the CRM frontend renders.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agent.guardrails import TenantGuardError, enforce_tenant_scope
from app.agent.state import AgentContext, ModeResult
from app.core.llm import get_llm_client
from app.services.adapters import get_adapter
from app.utils.json_safety import make_json_safe
from app.utils.prompt_builder import _format_schema

logger = logging.getLogger(__name__)

_ROW_CAP = 500
_VALID_CHARTS = {"bar", "line", "pie", "area", "scatter", "table", "number"}

_SYSTEM_TMPL = (
    "You translate a business question into ONE read-only SQL SELECT query for "
    "a multi-tenant CRM, plus a visualization spec.\n\n"
    "DATABASE SCHEMA:\n{schema}\n\n"
    "HARD RULES:\n"
    "1. SELECT only. Never INSERT/UPDATE/DELETE/DDL. No stacked statements.\n"
    "2. MULTI-TENANCY: every table that has a `company_id` column MUST be "
    "filtered by `company_id = {company_id}`. This is mandatory.\n"
    "3. Prefer human-readable columns over raw IDs; JOIN to resolve names.\n"
    "4. Always alias aggregates (COUNT(*) AS total, etc.).\n"
    "5. Add ORDER BY + LIMIT for 'top/most/highest' questions.\n\n"
    "Respond with ONLY a JSON object:\n"
    '{{"sql": "<query>", "explanation": "<one sentence>", '
    '"chart": {{"type": "bar|line|pie|area|scatter|table|number", '
    '"x": "<column for x-axis/category>", "y": "<column for value>", '
    '"aggregate": "<sum|count|avg|none>", "title": "<chart title>"}}}}'
)


class VizState(TypedDict, total=False):
    message: str
    company_id: int
    sql: str
    explanation: str
    chart: dict
    rows: list
    error: str


def _make_generate_node(ctx: AgentContext):
    schema_text = _format_schema(ctx.session.schema_context)

    def _node_generate(state: VizState) -> VizState:
        system = _SYSTEM_TMPL.format(schema=schema_text, company_id=state["company_id"])
        messages = [
            {"role": "system", "content": system},
            *ctx.session.get_llm_history(),
            {"role": "user", "content": state["message"]},
        ]
        result = get_llm_client().chat_completion_json(messages, temperature=0.1)
        state["sql"] = (result.get("sql") or "").strip()
        state["explanation"] = result.get("explanation", "")
        chart = result.get("chart") or {}
        if chart.get("type") not in _VALID_CHARTS:
            chart["type"] = "table"
        state["chart"] = chart
        if not state["sql"]:
            state["error"] = result.get("explanation") or "Could not generate a query."
        return state

    return _node_generate


def _node_validate(state: VizState) -> VizState:
    if state.get("error"):
        return state
    try:
        enforce_tenant_scope(state["sql"], state["company_id"])
    except TenantGuardError as exc:
        state["error"] = str(exc)
    return state


def _make_execute_node(ctx: AgentContext):
    def _node_execute(state: VizState) -> VizState:
        if state.get("error"):
            return state
        if not ctx.session.has_db_connection:
            state["error"] = "Session has no db_url; cannot execute the query."
            return state

        adapter = None
        try:
            adapter = get_adapter(ctx.session.query_type, ctx.session.db_url)
            rows = adapter.execute(state["sql"]) if adapter else []
            state["rows"] = make_json_safe(rows[:_ROW_CAP])
        except Exception as exc:
            logger.exception("VISUALIZE execution failed")
            state["error"] = str(exc)
        finally:
            if adapter is not None:
                try:
                    adapter.close()
                except Exception:
                    logger.debug("adapter close failed", exc_info=True)
        return state

    return _node_execute


def _build_graph(ctx: AgentContext):
    g = StateGraph(VizState)
    g.add_node("generate", _make_generate_node(ctx))
    g.add_node("validate", _node_validate)
    g.add_node("execute", _make_execute_node(ctx))
    g.add_edge(START, "generate")
    g.add_edge("generate", "validate")
    g.add_edge("validate", "execute")
    g.add_edge("execute", END)
    return g.compile()


def run_visualize(ctx: AgentContext, message: str) -> ModeResult:
    """Generate, tenant-scope, and execute a read-only insight query."""
    company_id = ctx.request.company_id
    if company_id is None:
        return ModeResult(
            mode="visualize",
            content="Cannot run insights without a company context (missing companyId in token).",
            error="missing_company_id",
        )

    final = _build_graph(ctx).invoke({"message": message, "company_id": company_id})

    if final.get("error"):
        return ModeResult(
            mode="visualize",
            content=f"I couldn't run that insight: {final['error']}",
            executed_query=final.get("sql"),
            error=final["error"],
        )

    chart: dict[str, Any] = final.get("chart") or {}
    rows = final.get("rows") or []
    content = final.get("explanation") or f"Returned {len(rows)} row(s)."
    return ModeResult(
        mode="visualize",
        content=content,
        executed_query=final.get("sql"),
        query_result=rows,
        visualization={
            "chart_type": chart.get("type", "table"),
            "x": chart.get("x"),
            "y": chart.get("y"),
            "aggregate": chart.get("aggregate", "none"),
            "title": chart.get("title"),
            "row_count": len(rows),
        },
    )
