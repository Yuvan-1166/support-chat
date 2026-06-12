"""Thin synchronous HTTP client over the CRM REST API.

Constructed *per request* with the forwarded employee JWT so every call is
made with the signed-in employee's identity and permissions.  Tool modules
call the verb helpers (``get``/``post``/``patch``/``put``/``delete``) with an
endpoint path from :mod:`app.crm.endpoints`.

Synchronous on purpose: the agent graph runs inside ``asyncio.to_thread`` (see
the chat route), and ``httpx.Client`` keeps the tool code simple and reusable
from the MCP server too.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CRMError(Exception):
    """Raised when a CRM API call returns a non-2xx status.

    Carries the HTTP status and parsed body so tools can surface a useful,
    structured error back to the agent instead of a raw stack trace.
    """

    def __init__(self, status_code: int, message: str, body: Any = None) -> None:
        super().__init__(f"CRM API {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class CRMClient:
    """Per-employee CRM API client.

    Parameters
    ----------
    jwt:
        The forwarded employee JWT — sent as ``Authorization: Bearer``.
    base_url:
        Override the configured ``CRM_BASE_URL`` (mainly for tests).
    timeout:
        Per-request timeout in seconds.
    """

    def __init__(
        self,
        jwt: str,
        *,
        base_url: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self._jwt = jwt
        self._base_url = (base_url or get_settings().CRM_BASE_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {jwt}",
                "Content-Type": "application/json",
            },
        )

    # ── context-manager support ──────────────────────────────────────────
    def __enter__(self) -> "CRMClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            logger.debug("CRMClient close failed", exc_info=True)

    # ── core request ─────────────────────────────────────────────────────
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Any:
        # Drop None-valued query params / body keys so we don't send literal nulls.
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        clean_json = {k: v for k, v in (json or {}).items() if v is not None} if json is not None else None

        logger.info("CRM %s %s", method, path)
        resp = self._client.request(
            method,
            path,
            params=clean_params or None,
            json=clean_json,
        )

        body: Any
        try:
            body = resp.json()
        except ValueError:
            body = resp.text

        if resp.is_success:
            return body

        # The CRM envelope is { success: false, message }.
        message = body.get("message") if isinstance(body, dict) else str(body)
        raise CRMError(resp.status_code, message or "request failed", body)

    # ── verb helpers ─────────────────────────────────────────────────────
    def get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: Optional[dict[str, Any]] = None) -> Any:
        return self._request("POST", path, json=json)

    def patch(self, path: str, *, json: Optional[dict[str, Any]] = None) -> Any:
        return self._request("PATCH", path, json=json)

    def put(self, path: str, *, json: Optional[dict[str, Any]] = None) -> Any:
        return self._request("PUT", path, json=json)

    def delete(self, path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        return self._request("DELETE", path, params=params)
