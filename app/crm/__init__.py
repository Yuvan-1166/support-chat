"""CRM integration package — HTTP client + endpoint constants.

AGENT-mode tools call back into the CRM REST API *as the signed-in employee*
using the JWT forwarded by the CRM's ``/api/assistant`` proxy.
"""

from app.crm.client import CRMClient, CRMError

__all__ = ["CRMClient", "CRMError"]
