"""CRM REST API endpoint paths (relative to ``CRM_BASE_URL``).

Mirrors ``CRM_BACKEND_API.md``.  Centralising the paths here keeps the tool
modules declarative and makes endpoint changes a one-line edit.  ``{}``
placeholders are filled with ``str.format`` by the caller.
"""

from __future__ import annotations

# ── Contacts / lifecycle ───────────────────────────────────────────────────
CONTACTS = "/api/contacts"
CONTACTS_SEARCH = "/api/contacts/search"
CONTACT = "/api/contacts/{contact_id}"
CONTACT_PROMOTE_MQL = "/api/contacts/{contact_id}/promote-mql"
CONTACT_PROMOTE_SQL = "/api/contacts/{contact_id}/promote-sql"
CONTACT_OPPORTUNITY = "/api/contacts/{contact_id}/opportunity"
CONTACT_FINANCIALS = "/api/contacts/{contact_id}/financials"

# ── Opportunities / Deals ──────────────────────────────────────────────────
OPPORTUNITIES = "/api/opportunities"
OPPORTUNITY = "/api/opportunities/{opportunity_id}"
OPPORTUNITY_WON = "/api/opportunities/{opportunity_id}/won"
OPPORTUNITY_LOST = "/api/opportunities/{opportunity_id}/lost"
DEALS = "/api/deals"
DEAL = "/api/deals/{deal_id}"

# ── Tasks / Calendar / Meet ────────────────────────────────────────────────
TASKS = "/api/tasks"
TASK = "/api/tasks/{task_id}"
TASKS_TODAY = "/api/tasks/today"
TASKS_WEEK = "/api/tasks/week"
TASKS_OVERDUE = "/api/tasks/overdue"
TASKS_UPCOMING = "/api/tasks/upcoming"
TASKS_CALENDAR = "/api/tasks/calendar"
TASK_RESOLVE = "/api/tasks/{task_id}/resolve"
TASK_MEET_LINK = "/api/tasks/{task_id}/meet-link"
CALENDAR_SYNC_STATUS = "/api/tasks/calendar-sync/status"
CALENDAR_SYNC_TASK = "/api/tasks/calendar-sync/{task_id}"

# ── Email / Templates ──────────────────────────────────────────────────────
EMAILS = "/api/emails"
EMAILS_FOR_CONTACT = "/api/emails/contact/{contact_id}"
EMAIL_CONNECTION_STATUS = "/api/emails/connection-status"
EMAIL_TEMPLATES = "/api/email-templates"
EMAIL_TEMPLATE_PREVIEW = "/api/email-templates/{template_id}/preview"

# ── Sequences (drip campaigns) ─────────────────────────────────────────────
SEQUENCES = "/api/sequences/"
SEQUENCE = "/api/sequences/{sequence_id}"
SEQUENCE_ENROLL = "/api/sequences/{sequence_id}/enroll"
SEQUENCE_ENROLLMENTS = "/api/sequences/{sequence_id}/enrollments"
ENROLLMENT_PAUSE = "/api/sequences/{sequence_id}/enrollments/{enrollment_id}/pause"
ENROLLMENT_RESUME = "/api/sequences/{sequence_id}/enrollments/{enrollment_id}/resume"

# ── Outreach (RAG-grounded campaigns) ──────────────────────────────────────
OUTREACH_CONTACTS = "/api/outreach/contacts"
OUTREACH_GENERATE = "/api/outreach/generate"
OUTREACH_SEND = "/api/outreach/send"

# ── Automations / Triggers ─────────────────────────────────────────────────
AUTOMATIONS = "/api/automations/"
AUTOMATION = "/api/automations/{automation_id}"
AUTOMATION_TOGGLE = "/api/automations/{automation_id}/toggle"
AUTOMATION_METADATA = "/api/automations/metadata"
AUTOMATION_LOGS = "/api/automations/logs"
AUTOMATION_OWN_LOGS = "/api/automations/{automation_id}/logs"
