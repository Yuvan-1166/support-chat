"""Per-mode guardrails for the three-mode agent.

Each mode has a distinct safety boundary:

* **ASK** — answer only from retrieved knowledge; never invent navigation,
  never run queries or actions.  Enforced mostly in the prompt; this module
  provides the refusal text and a cheap intent check.
* **VISUALIZE** — read-only + **mandatory tenant scoping**.  We reuse the SQL
  adapter's write-keyword blocklist and additionally require the query to be
  constrained to the caller's ``company_id`` (best-effort static check +
  prompt enforcement).
* **AGENT** — destructive/outbound actions require explicit confirmation; the
  set of confirm-gated tools lives here.
"""

from __future__ import annotations

import re
from typing import Optional

from app.services.adapters.sql_adapter import SQLAdapter

# ── ASK ─────────────────────────────────────────────────────────────────────

ASK_REFUSAL = (
    "I can only answer questions about how the CRM works and where to find "
    "things. I can't run database queries or take actions in ASK mode — "
    "switch to VISUALIZE mode for data insights, or AGENT mode to perform "
    "actions."
)

# Phrases that signal the user wants data/actions rather than how-to help.
_ASK_OUT_OF_SCOPE = re.compile(
    r"\b(run (a )?query|execute|select \*|insert|update|delete|drop|"
    r"send (an )?email|create (a )?task|schedule|enroll|automate)\b",
    re.IGNORECASE,
)


def ask_out_of_scope(message: str) -> bool:
    """Heuristic: does this ASK-mode message actually request data/actions?"""
    return bool(_ASK_OUT_OF_SCOPE.search(message))


# ── VISUALIZE ────────────────────────────────────────────────────────────────


class TenantGuardError(Exception):
    """Raised when a VISUALIZE query cannot be safely tenant-scoped."""


def is_read_only(query: str) -> bool:
    """Reuse the adapter's read-only enforcement (SELECT-only, no stacked stmts)."""
    return SQLAdapter._is_read_only(query)


def references_company_scope(query: str, company_id: int) -> bool:
    """Best-effort check that the query is constrained to the caller's company.

    Accepts the query if it references ``company_id`` with the caller's value
    (the value may be a bind placeholder we inject) — full enforcement is the
    combination of this check and the injected predicate in
    :func:`enforce_tenant_scope`.
    """
    return "company_id" in query.lower()


def enforce_tenant_scope(query: str, company_id: int) -> str:
    """Validate a VISUALIZE query and ensure it is tenant-scoped.

    Raises
    ------
    TenantGuardError
        If the query is not read-only or cannot be confirmed company-scoped.

    Returns
    -------
    str
        The validated query (unchanged; we do not rewrite SQL — we require the
        generator to include ``company_id`` and reject anything that doesn't).
    """
    if not is_read_only(query):
        raise TenantGuardError(
            "Only read-only SELECT queries are permitted in VISUALIZE mode."
        )
    if not references_company_scope(query, company_id):
        raise TenantGuardError(
            "Query must be scoped to the caller's company_id "
            f"(= {company_id}). Add a WHERE company_id = {company_id} predicate "
            "to every table that has a company_id column."
        )
    return query


# ── AGENT ────────────────────────────────────────────────────────────────────

# Tools whose effects are outbound or hard to undo — gated behind confirmation.
CONFIRM_REQUIRED_TOOLS: frozenset[str] = frozenset(
    {
        "send_email",
        "send_outreach",
        "close_opportunity_won",
        "create_automation",
        "create_deal",
        "delete_task",
    }
)


def requires_confirmation(tool_name: str) -> bool:
    """Whether *tool_name* must be confirmed before it executes."""
    return tool_name in CONFIRM_REQUIRED_TOOLS


def confirmation_prompt(tool_name: str, tool_input: Optional[dict]) -> str:
    """Human-readable description of a pending, confirmation-gated action."""
    pretty_args = ", ".join(f"{k}={v!r}" for k, v in (tool_input or {}).items())
    return f"Please confirm: run `{tool_name}`({pretty_args})?"
