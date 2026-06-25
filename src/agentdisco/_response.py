"""Shared HTTP response handling for the sync + async clients.

`parse_json` extracts the JSON body on success and maps 4xx/5xx onto the
typed exception hierarchy. It's pure (no I/O, no awaiting) — httpx has
already read the body by the time a non-streaming response is returned, on
both the sync and async paths — so a single implementation serves both
clients.
"""

from __future__ import annotations

from typing import Any

import httpx

from agentdisco.exceptions import (
    AgentDiscoError,
    ApiError,
    InvalidUrlError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
)


def parse_json(response: httpx.Response) -> dict[str, Any]:
    """Return the JSON object body, or raise the right typed exception."""
    if 200 <= response.status_code < 300:
        try:
            body = response.json()
        except ValueError as exc:
            raise AgentDiscoError(
                f"server returned {response.status_code} with non-JSON body",
            ) from exc
        if not isinstance(body, dict):
            raise AgentDiscoError(
                f"server returned {response.status_code} with non-object JSON",
            )
        return body

    payload: dict[str, Any] = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            payload = parsed
    except ValueError:
        pass

    message = str(payload.get("message") or payload.get("error") or response.text or "").strip()
    if message == "":
        message = f"HTTP {response.status_code} from Agent Disco API"
    error_code = payload.get("error") if isinstance(payload.get("error"), str) else None

    status = response.status_code
    kwargs: dict[str, Any] = {
        "status_code": status,
        "error_code": error_code,
        "payload": payload,
    }

    if status == 400 and error_code == "invalid_url":
        raise InvalidUrlError(message, **kwargs)
    if status == 401:
        raise UnauthorizedError(message, **kwargs)
    if status == 404:
        raise NotFoundError(message, **kwargs)
    if status == 429:
        retry_after = response.headers.get("Retry-After")
        retry_after_seconds = (
            int(retry_after) if retry_after and retry_after.isdigit() else None
        )
        raise RateLimitedError(
            message,
            retry_after_seconds=retry_after_seconds,
            **kwargs,
        )

    raise ApiError(message, **kwargs)
