"""Dataclass response models — what the REST endpoints return.

Only the load-bearing fields are modelled; the full JSON payload is
always available on `raw` for anything the SDK doesn't surface
directly. That gives us room to grow the API without breaking existing
callers who rely on specific fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Scan:
    """A scan (queued, running, or completed).

    `grade` and `score` are `None` while the scan is still in flight;
    poll `get_scan(id)` until `status == "completed"`.
    """

    id: str
    status: str
    result_url: str
    grade: str | None
    score: int | None
    raw: dict[str, Any]

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> Scan:
        return cls(
            id=str(payload["id"]),
            status=str(payload["status"]),
            result_url=str(payload.get("resultUrl") or payload.get("statusUrl") or ""),
            grade=payload.get("grade"),
            score=payload.get("score"),
            raw=payload,
        )


@dataclass(frozen=True)
class Website:
    """Summary view of a scanned host — latest grade + activity."""

    host: str
    latest_grade: str | None
    latest_score: int | None
    last_scanned_at: str | None
    scan_count: int
    raw: dict[str, Any]

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> Website:
        return cls(
            host=str(payload["host"]),
            latest_grade=payload.get("latestGrade"),
            latest_score=payload.get("latestScore"),
            last_scanned_at=payload.get("lastScannedAt"),
            scan_count=int(payload.get("scanCount", 0)),
            raw=payload,
        )


@dataclass(frozen=True)
class ApiKey:
    """A freshly-minted API key.

    `token` is the full plaintext — the server returns this exactly
    ONCE (at mint time) and keeps only a SHA-256 hash. Store the
    token immediately; losing it means minting a fresh one.

    `token_prefix` is the first 10 chars (`ak_XXXXXXX`) and is safe to
    display in logs or dashboards; unlike `token`, it can't be used
    to authenticate.
    """

    id: str
    token: str
    token_prefix: str
    rate_limit_tier: str
    created_at: str
    raw: dict[str, Any]

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> ApiKey:
        return cls(
            id=str(payload["id"]),
            token=str(payload["token"]),
            token_prefix=str(payload["tokenPrefix"]),
            rate_limit_tier=str(payload["rateLimitTier"]),
            created_at=str(payload["createdAt"]),
            raw=payload,
        )
