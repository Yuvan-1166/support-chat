"""AGENT-mode tools: contacts lifecycle, opportunities, and deals."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool, tool

from app.agent.state import AgentContext
from app.agent.tools.base import call, gate
from app.crm import endpoints as ep
from app.crm.client import CRMClient


def build_contact_tools(crm: CRMClient, ctx: AgentContext) -> list[StructuredTool]:
    @tool
    def search_contacts(query: str = "", limit: int = 20) -> str:
        """Search the company's contacts by name/email/phone. Returns matching contacts."""
        return call(lambda: crm.get(ep.CONTACTS_SEARCH, params={"q": query, "limit": limit}))

    @tool
    def get_contact(contact_id: int) -> str:
        """Fetch a single contact's full details by its numeric id."""
        return call(lambda: crm.get(ep.CONTACT.format(contact_id=contact_id)))

    @tool
    def list_contacts(status: Optional[str] = None, limit: int = 50, offset: int = 0) -> str:
        """List contacts for the company, optionally filtered by lifecycle status
        (LEAD, MQL, SQL, CUSTOMER, EVANGELIST, DORMANT)."""
        return call(
            lambda: crm.get(ep.CONTACTS, params={"status": status, "limit": limit, "offset": offset})
        )

    @tool
    def create_contact(name: str, email: Optional[str] = None, phone: Optional[str] = None) -> str:
        """Create a new lead/contact. Triggers the CRM's welcome-email flow."""
        return call(lambda: crm.post(ep.CONTACTS, json={"name": name, "email": email, "phone": phone}))

    @tool
    def update_contact(contact_id: int, fields: dict) -> str:
        """Update fields on a contact. `fields` is a dict of column->value to change."""
        return call(lambda: crm.patch(ep.CONTACT.format(contact_id=contact_id), json=fields))

    @tool
    def promote_to_mql(contact_id: int) -> str:
        """Promote a LEAD contact to MQL (Marketing Qualified Lead)."""
        return call(lambda: crm.patch(ep.CONTACT_PROMOTE_MQL.format(contact_id=contact_id)))

    @tool
    def promote_to_sql(contact_id: int) -> str:
        """Promote an MQL contact to SQL (Sales Qualified Lead)."""
        return call(lambda: crm.patch(ep.CONTACT_PROMOTE_SQL.format(contact_id=contact_id)))

    @tool
    def create_opportunity(contact_id: int, expected_value: float) -> str:
        """Create an opportunity from an SQL contact with an expected deal value."""
        return call(
            lambda: crm.post(
                ep.CONTACT_OPPORTUNITY.format(contact_id=contact_id),
                json={"expectedValue": expected_value},
            )
        )

    @tool
    def close_opportunity_won(opportunity_id: int, deal_value: float) -> str:
        """Mark an opportunity WON (creates a deal, converts contact to CUSTOMER).
        Confirmation-gated."""
        pend = gate(ctx, "close_opportunity_won", {"opportunity_id": opportunity_id, "deal_value": deal_value})
        if pend:
            return pend
        return call(
            lambda: crm.post(ep.OPPORTUNITY_WON.format(opportunity_id=opportunity_id), json={"dealValue": deal_value})
        )

    @tool
    def close_opportunity_lost(opportunity_id: int, reason: Optional[str] = None) -> str:
        """Mark an opportunity LOST (moves contact to DORMANT)."""
        return call(
            lambda: crm.post(ep.OPPORTUNITY_LOST.format(opportunity_id=opportunity_id), json={"reason": reason})
        )

    @tool
    def contact_financials(contact_id: int) -> str:
        """Get a contact's opportunities and deals (revenue/pipeline figures)."""
        return call(lambda: crm.get(ep.CONTACT_FINANCIALS.format(contact_id=contact_id)))

    return [
        search_contacts,
        get_contact,
        list_contacts,
        create_contact,
        update_contact,
        promote_to_mql,
        promote_to_sql,
        create_opportunity,
        close_opportunity_won,
        close_opportunity_lost,
        contact_financials,
    ]
