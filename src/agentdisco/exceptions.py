"""Exception hierarchy for the Agent Disco SDK.

All SDK-raised exceptions inherit `AgentDiscoError` so a caller can
do a single broad catch. More specific subtypes (`NotFoundError`,
`RateLimitedError`, etc.) let callers react differently to recoverable
vs unrecoverable failures.

Network-layer errors (connection timeout, DNS failure) leak through
as raw `httpx` exceptions — we don't wrap them because the failure
mode is platform, not API. Application-layer errors (4xx/5xx) are
wrapped into the `ApiError` branch.
"""

from __future__ import annotations

from typing import Any


class AgentDiscoError(Exception):
    """Root of the SDK exception hierarchy."""


class ApiError(AgentDiscoError):
    """An HTTP response carried a 4xx or 5xx status.

    `status_code` is the HTTP status; `error_code` is the server's
    `error` field from the JSON body when present (e.g. `invalid_url`,
    `not_found`); `payload` is the parsed JSON for anything the SDK
    didn't model.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.payload = payload or {}


class InvalidUrlError(ApiError):
    """HTTP 400 with error=invalid_url — the URL failed server validation."""


class UnauthorizedError(ApiError):
    """HTTP 401 — missing or invalid auth (ops endpoints only)."""


class NotFoundError(ApiError):
    """HTTP 404 — unknown scan id or host."""


class RateLimitedError(ApiError):
    """HTTP 429 — quota exceeded.

    `retry_after_seconds` is parsed from the `Retry-After` response
    header when present; callers can sleep that long and retry.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retry_after_seconds: int | None = None,
        error_code: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            payload=payload,
        )
        self.retry_after_seconds = retry_after_seconds
