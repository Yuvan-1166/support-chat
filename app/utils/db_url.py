"""Utilities for handling connection URLs passed by API clients."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def split_ssl_ca_b64_from_url(db_url: str) -> tuple[str, str]:
    """Extract ``ssl_ca_b64`` from URL query parameters.

    Returns
    -------
    tuple[str, str]
        (clean_url_without_ssl_ca_b64, ssl_ca_b64_or_empty)
    """
    parsed = urlparse(db_url)
    params = parse_qsl(parsed.query, keep_blank_values=True)

    ssl_ca_b64 = ""
    kept: list[tuple[str, str]] = []
    for key, value in params:
        if key.lower() == "ssl_ca_b64" and not ssl_ca_b64:
            ssl_ca_b64 = value
            continue
        kept.append((key, value))

    clean_query = urlencode(kept, doseq=True)
    clean_url = urlunparse(parsed._replace(query=clean_query))
    return clean_url, ssl_ca_b64


def split_ssl_options_from_url(db_url: str) -> tuple[str, str, bool | None]:
    """Extract ssl-related overrides from URL query params.

    Supported overrides:
    - ``ssl_ca_b64``: base64-encoded PEM certificate
    - ``ssl_verify``: one of ``true/false/1/0/yes/no/on/off``

    Returns
    -------
    tuple[str, str, bool | None]
        (clean_url, ssl_ca_b64, ssl_verify_override)
    """
    parsed = urlparse(db_url)
    params = parse_qsl(parsed.query, keep_blank_values=True)

    ssl_ca_b64 = ""
    ssl_verify: bool | None = None
    kept: list[tuple[str, str]] = []

    for key, value in params:
        key_lower = key.lower()
        if key_lower == "ssl_ca_b64" and not ssl_ca_b64:
            ssl_ca_b64 = value
            continue

        if key_lower == "ssl_verify" and ssl_verify is None:
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                ssl_verify = True
            elif normalized in {"0", "false", "no", "off"}:
                ssl_verify = False
            continue

        kept.append((key, value))

    clean_query = urlencode(kept, doseq=True)
    clean_url = urlunparse(parsed._replace(query=clean_query))
    return clean_url, ssl_ca_b64, ssl_verify
