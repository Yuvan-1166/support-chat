"""Chat API endpoint — three-mode agent (ask · visualize · agent)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.agent import run_mode
from app.agent.state import AgentContext
from app.core.llm import get_llm_client
from app.core.request_context import InvalidIdentityError, build_request_context
from app.core.security import require_api_key
from app.db import get_db
from app.db.models import ToolAuditModel
from app.core.request_context import RequestContext
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatMode,
    PendingActionModel,
    VisualizationSpec,
)
from app.services.sql_session_store import get_session_store
from app.services.translator import QueryTranslator
from app.utils.json_safety import make_json_safe

logger = logging.getLogger(__name__)


def _audit_tool_results(
    db: DBSession,
    *,
    session_id: str,
    ctx: RequestContext,
    reasoning: list[dict],
    tool_results: list[dict],
) -> None:
    """Write one ``tool_audit`` row per executed tool (best-effort).

    Pairs the reasoning steps (which carry tool name + input) with the tool
    results positionally; never raises so a bookkeeping failure can't break the
    user-facing response.
    """
    try:
        for i, tr in enumerate(tool_results):
            meta = reasoning[i] if i < len(reasoning) else {}
            result = tr.get("result")
            success = "true"
            if isinstance(result, dict) and result.get("success") is False:
                success = "false"
            db.add(
                ToolAuditModel(
                    session_id=session_id,
                    company_id=ctx.company_id,
                    emp_id=ctx.emp_id,
                    tool_name=meta.get("tool_name") or "unknown",
                    tool_input=make_json_safe(meta.get("tool_input")),
                    result=make_json_safe(result),
                    success=success,
                )
            )
        db.commit()
    except Exception:  # pragma: no cover - audit must never break the request
        logger.exception("Failed to write tool audit log")
        db.rollback()

router = APIRouter(prefix="/sessions", tags=["Chat"])


@router.post(
    "/{session_id}/chat",
    response_model=ChatMessageResponse,
    summary="Send a chat message (ask | visualize | agent)",
)
async def send_message(
    session_id: str,
    body: ChatMessageRequest,
    authorization: str | None = Header(default=None),
    _api_key: str = Depends(require_api_key),
    db: DBSession = Depends(get_db),
):
    """Handle one conversation turn in the selected mode.

    * **ask** — RAG-grounded help & navigation (no DB, no actions).
    * **visualize** — generate + execute a read-only, tenant-scoped query and
      return rows plus a chart spec.
    * **agent** — autonomous tool use against the CRM API (as the employee
      identified by the forwarded JWT). Destructive actions return
      ``requires_confirmation``; resend with ``confirmed: true`` to execute.

    The employee JWT forwarded by the CRM (``Authorization`` header) provides
    the identity used for AGENT actions and VISUALIZE tenant scoping. ASK mode
    works without it.
    """
    store = get_session_store(db)
    session = store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired.",
        )

    # Identity from the forwarded JWT. Required for visualize/agent; ASK can run
    # without it (with a placeholder context).
    try:
        ctx_identity = build_request_context(authorization)
    except InvalidIdentityError as exc:
        if body.mode == ChatMode.ASK:
            from app.core.request_context import RequestContext

            ctx_identity = RequestContext(raw_jwt="", emp_id=None, company_id=None, role=None)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Valid employee token required for {body.mode.value} mode: {exc}",
            )

    agent_ctx = AgentContext(
        session=session,
        request=ctx_identity,
        translator=QueryTranslator(get_llm_client()),
        confirmed=body.confirmed,
    )

    # Persist the user turn before running so it is part of history.
    store.add_message(session.session_id, "user", body.message)

    result = await run_mode(body.mode, agent_ctx, body.message)

    # Persist the assistant turn (with the executed query/result when present).
    store.add_message(
        session_id=session.session_id,
        role="assistant",
        content=result.content,
        query=result.executed_query,
        query_result=result.query_result,
    )

    # AGENT mode: record a tenant-isolated audit trail of tool executions.
    if body.mode == ChatMode.AGENT and result.tool_results:
        _audit_tool_results(
            db,
            session_id=session.session_id,
            ctx=ctx_identity,
            reasoning=result.agent_reasoning or [],
            tool_results=result.tool_results,
        )

    return ChatMessageResponse(
        role="assistant",
        mode=body.mode,
        content=result.content,
        query=result.executed_query,
        query_result=result.query_result,
        visualization=VisualizationSpec(**result.visualization) if result.visualization else None,
        agent_reasoning=result.agent_reasoning or None,
        tool_results=result.tool_results or None,
        requires_confirmation=result.requires_confirmation,
        pending_action=(
            PendingActionModel(
                tool=result.pending_action.tool,
                tool_input=result.pending_action.tool_input,
                prompt=result.pending_action.prompt,
            )
            if result.pending_action
            else None
        ),
        sources=result.sources or None,
        error=result.error,
    )
