"""Per-request identity context derived from the forwarded employee JWT.

The CRM's ``/api/assistant`` proxy forwards the signed-in employee's
``Authorization: Bearer <jwt>`` header to this service.  We decode it once at
the edge to obtain ``{emp_id, company_id, role}`` and carry both the raw token
(so AGENT-mode tools can call the CRM API *as that employee*) and the decoded
claims (so VISUALIZE-mode can tenant-scope queries to ``company_id``).

When ``JWT_SECRET`` is configured the signature is verified; otherwise the
token is decoded without verification (the CRM is a trusted upstream caller).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import jwt

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class InvalidIdentityError(Exception):
    """Raised when a forwarded JWT is missing, malformed, or fails verification."""


@dataclass(frozen=True)
class RequestContext:
    """Identity + credentials for a single inbound chat request."""

    raw_jwt: str
    emp_id: Optional[int]
    company_id: Optional[int]
    role: Optional[str]
    name: Optional[str] = None

    @property
    def has_company(self) -> bool:
        return self.company_id is not None

    @property
    def is_admin(self) -> bool:
        return (self.role or "").upper() == "ADMIN"


def _extract_bearer(authorization: Optional[str]) -> str:
    """Pull the raw token out of an ``Authorization: Bearer <token>`` header."""
    if not authorization:
        raise InvalidIdentityError("Missing Authorization header.")
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    # Tolerate a bare token without the "Bearer " prefix.
    if len(parts) == 1:
        return parts[0]
    raise InvalidIdentityError("Malformed Authorization header.")


def _coerce_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_request_context(authorization: Optional[str]) -> RequestContext:
    """Decode the forwarded JWT into a :class:`RequestContext`.

    Looks for the CRM's claim names (``empId``/``companyId``/``role``) with
    snake_case fallbacks.  Raises :class:`InvalidIdentityError` on any failure
    so callers can return a clean 401.
    """
    token = _extract_bearer(authorization)
    settings = get_settings()

    try:
        if settings.JWT_SECRET:
            claims = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=settings.jwt_algorithms,
            )
        else:
            # Trusted-caller mode: decode without verifying the signature.
            claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise InvalidIdentityError(f"JWT decode failed: {exc}") from exc

    emp_id = _coerce_int(claims.get("empId", claims.get("emp_id")))
    company_id = _coerce_int(claims.get("companyId", claims.get("company_id")))
    role = claims.get("role")
    name = claims.get("name")

    logger.debug(
        "Request context: emp_id=%s company_id=%s role=%s", emp_id, company_id, role
    )
    return RequestContext(
        raw_jwt=token,
        emp_id=emp_id,
        company_id=company_id,
        role=role,
        name=name,
    )
