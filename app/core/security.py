"""API-key authentication dependency."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate the ``X-API-Key`` header against configured keys.

    In *development* mode with no keys configured the check is skipped
    so local testing is frictionless.
    """
    allowed = settings.api_key_list

    # In dev mode with no keys configured, allow all requests
    if settings.is_development and not allowed:
        return "dev-no-auth"

    if not api_key or api_key not in allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return api_key
