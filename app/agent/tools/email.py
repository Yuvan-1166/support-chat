"""AGENT-mode tools: email, templates, sequences, and outreach campaigns."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool, tool

from app.agent.state import AgentContext
from app.agent.tools.base import call, gate
from app.crm import endpoints as ep
from app.crm.client import CRMClient


def build_email_tools(crm: CRMClient, ctx: AgentContext) -> list[StructuredTool]:
    @tool
    def send_email(contact_id: int, subject: str, body: str, cc: Optional[str] = None) -> str:
        """Send an email to a contact via the employee's connected Gmail (queued).
        Confirmation-gated."""
        payload = {"contactId": contact_id, "subject": subject, "body": body, "cc": cc}
        pend = gate(ctx, "send_email", payload)
        if pend:
            return pend
        return call(lambda: crm.post(ep.EMAILS, json=payload))

    @tool
    def email_connection_status() -> str:
        """Check whether the employee has a connected Gmail account."""
        return call(lambda: crm.get(ep.EMAIL_CONNECTION_STATUS))

    @tool
    def email_history(contact_id: int) -> str:
        """Get the history of CRM emails sent to a contact."""
        return call(lambda: crm.get(ep.EMAILS_FOR_CONTACT.format(contact_id=contact_id)))

    @tool
    def list_email_templates(category: Optional[str] = None, search: Optional[str] = None) -> str:
        """List the company's email templates, optionally filtered by category/search."""
        return call(lambda: crm.get(ep.EMAIL_TEMPLATES, params={"category": category, "search": search}))

    @tool
    def preview_template(template_id: int, variables: dict) -> str:
        """Render an email template with the given variable map (e.g. {contact_name: 'Jane'})."""
        return call(lambda: crm.post(ep.EMAIL_TEMPLATE_PREVIEW.format(template_id=template_id), json=variables))

    @tool
    def list_sequences(status: Optional[str] = None, search: Optional[str] = None) -> str:
        """List drip-campaign sequences for the company."""
        return call(lambda: crm.get(ep.SEQUENCES, params={"status": status, "search": search}))

    @tool
    def create_sequence(name: str, description: Optional[str] = None, steps: Optional[list] = None) -> str:
        """Create a multi-step email sequence (drip campaign)."""
        return call(lambda: crm.post(ep.SEQUENCES, json={"name": name, "description": description, "steps": steps or []}))

    @tool
    def enroll_in_sequence(sequence_id: int, contact_ids: list[int]) -> str:
        """Enroll one or more contacts into a sequence."""
        return call(lambda: crm.post(ep.SEQUENCE_ENROLL.format(sequence_id=sequence_id), json={"contactIds": contact_ids}))

    @tool
    def pause_enrollment(sequence_id: int, enrollment_id: int, reason: Optional[str] = None) -> str:
        """Pause a contact's enrollment in a sequence."""
        return call(
            lambda: crm.post(
                ep.ENROLLMENT_PAUSE.format(sequence_id=sequence_id, enrollment_id=enrollment_id),
                json={"reason": reason},
            )
        )

    @tool
    def resume_enrollment(sequence_id: int, enrollment_id: int) -> str:
        """Resume a paused enrollment in a sequence."""
        return call(
            lambda: crm.post(ep.ENROLLMENT_RESUME.format(sequence_id=sequence_id, enrollment_id=enrollment_id))
        )

    @tool
    def generate_outreach(contact_ids: list[int], employee_intent: str, from_status: str, to_status: str) -> str:
        """Generate personalized, RAG-grounded outreach email drafts for contacts
        to move them from one lifecycle status to another. Returns drafts to review."""
        return call(
            lambda: crm.post(
                ep.OUTREACH_GENERATE,
                json={
                    "contactIds": contact_ids,
                    "employeeIntent": employee_intent,
                    "fromStatus": from_status,
                    "toStatus": to_status,
                },
            )
        )

    @tool
    def send_outreach(emails: list[dict]) -> str:
        """Send reviewed outreach emails. Each item: {contactId, to, subject, body}.
        Confirmation-gated."""
        pend = gate(ctx, "send_outreach", {"count": len(emails)})
        if pend:
            return pend
        return call(lambda: crm.post(ep.OUTREACH_SEND, json={"emails": emails}))

    return [
        send_email,
        email_connection_status,
        email_history,
        list_email_templates,
        preview_template,
        list_sequences,
        create_sequence,
        enroll_in_sequence,
        pause_enrollment,
        resume_enrollment,
        generate_outreach,
        send_outreach,
    ]
