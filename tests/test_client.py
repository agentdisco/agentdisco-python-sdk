"""Tests for the AgentDisco client.

Uses httpx's MockTransport to stub the HTTP layer. Real agentdisco.io
isn't touched — tests need to be hermetic (CI without network,
stable output, fast execution).

Pattern: each test builds a `MockTransport(handler)` where `handler`
is a callable that maps request → response. The client is
constructed with `transport=transport`, which pipes all HTTP through
the stub without any real I/O.
"""

from __future__ import annotations

import json

import httpx
import pytest

from agentdisco import (
    AgentDisco,
    AgentDiscoError,
    ApiError,
    InvalidUrlError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
)


def make_transport(handler):
    """Convenience wrapper: accept a `(request) -> httpx.Response` callable."""
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------
# Scan submit
# ---------------------------------------------------------------


def test_submit_scan_returns_scan_dataclass():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/scans"
        body = json.loads(request.content)
        assert body == {"url": "https://example.com"}
        return httpx.Response(
            202,
            json={
                "id": "019d0000-0000-7000-8000-000000000001",
                "status": "queued",
                "statusUrl": "/api/v1/scans/019d0000-0000-7000-8000-000000000001",
                "resultUrl": "/report/example.com",
                "grade": None,
                "score": None,
            },
        )

    client = AgentDisco(transport=make_transport(handler))
    scan = client.submit_scan("https://example.com")

    assert scan.id == "019d0000-0000-7000-8000-000000000001"
    assert scan.status == "queued"
    assert scan.grade is None
    assert scan.score is None
    # The full payload stays reachable for fields the SDK doesn't surface.
    assert scan.raw["statusUrl"].startswith("/api/v1/scans/")


def test_submit_scan_sends_bearer_token_when_configured():
    received_headers = {}

    def handler(request):
        received_headers.update(dict(request.headers))
        return httpx.Response(202, json={
            "id": "019d0000-0000-7000-8000-000000000001",
            "status": "queued",
            "statusUrl": "/api/v1/scans/019d0000-0000-7000-8000-000000000001",
            "resultUrl": "/report/example.com",
            "grade": None,
            "score": None,
        })

    client = AgentDisco(token="ak_test12345", transport=make_transport(handler))
    client.submit_scan("https://example.com")

    assert received_headers.get("authorization") == "Bearer ak_test12345"


def test_submit_scan_raises_invalid_url_on_400_with_error_code():
    def handler(_request):
        return httpx.Response(400, json={
            "error": "invalid_url",
            "message": "URL must use http or https scheme.",
        })

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(InvalidUrlError) as exc:
        client.submit_scan("file:///etc/passwd")

    assert exc.value.status_code == 400
    assert exc.value.error_code == "invalid_url"
    assert "URL must use" in str(exc.value)


def test_submit_scan_raises_rate_limited_on_429_with_retry_after():
    def handler(_request):
        return httpx.Response(
            429,
            json={"error": "rate_limited", "message": "Anonymous scan quota exceeded."},
            headers={"Retry-After": "3600"},
        )

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(RateLimitedError) as exc:
        client.submit_scan("https://example.com")

    assert exc.value.retry_after_seconds == 3600
    assert exc.value.status_code == 429


# ---------------------------------------------------------------
# Scan polling
# ---------------------------------------------------------------


def test_get_scan_returns_completed_scan_with_grade():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/scans/abc"
        return httpx.Response(200, json={
            "id": "abc",
            "status": "completed",
            "statusUrl": "/api/v1/scans/abc",
            "resultUrl": "/report/example.com",
            "grade": "A",
            "score": 92,
        })

    client = AgentDisco(transport=make_transport(handler))
    scan = client.get_scan("abc")

    assert scan.status == "completed"
    assert scan.grade == "A"
    assert scan.score == 92


def test_get_scan_raises_not_found_on_404():
    def handler(_request):
        return httpx.Response(404, json={"error": "not_found", "message": "unknown scan id"})

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(NotFoundError):
        client.get_scan("does-not-exist")


# ---------------------------------------------------------------
# Website summary
# ---------------------------------------------------------------


def test_get_website_returns_summary():
    def handler(request):
        assert request.url.path == "/api/v1/websites/example.com"
        return httpx.Response(200, json={
            "host": "example.com",
            "latestGrade": "B",
            "latestScore": 72,
            "lastScannedAt": "2026-04-24T10:00:00+00:00",
            "scanCount": 4,
        })

    client = AgentDisco(transport=make_transport(handler))
    site = client.get_website("example.com")

    assert site.host == "example.com"
    assert site.latest_grade == "B"
    assert site.latest_score == 72
    assert site.scan_count == 4


def test_get_website_raises_not_found_for_unscanned_host():
    def handler(_request):
        return httpx.Response(404, json={"error": "not_found"})

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(NotFoundError):
        client.get_website("never-scanned.example")


# ---------------------------------------------------------------
# Mint key
# ---------------------------------------------------------------


def test_mint_key_returns_plaintext_once():
    """Plaintext is server-side one-shot; SDK just surfaces it faithfully."""

    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/keys"
        return httpx.Response(201, json={
            "id": "019d0000-0000-7000-8000-000000000002",
            "token": "ak_abcdefghijklmnopqrstuvwxyz01234567890ABCDEF",
            "tokenPrefix": "ak_abcdef",
            "rateLimitTier": "anonymous",
            "createdAt": "2026-04-24T10:00:00+00:00",
        })

    client = AgentDisco(transport=make_transport(handler))
    key = client.mint_key()

    assert key.token.startswith("ak_")
    assert len(key.token) == 46
    assert key.token_prefix == "ak_abcdef"
    assert key.rate_limit_tier == "anonymous"


def test_mint_key_rate_limited_after_five_per_hour():
    def handler(_request):
        return httpx.Response(429, json={"error": "rate_limited"}, headers={"Retry-After": "1800"})

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(RateLimitedError) as exc:
        client.mint_key()

    assert exc.value.retry_after_seconds == 1800


# ---------------------------------------------------------------
# Error handling — generic paths
# ---------------------------------------------------------------


def test_500_raises_generic_api_error():
    def handler(_request):
        return httpx.Response(500, text="Internal Server Error")

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(ApiError) as exc:
        client.submit_scan("https://example.com")

    # 500 is not one of the mapped specific subtypes; generic ApiError.
    specific = (InvalidUrlError, NotFoundError, RateLimitedError, UnauthorizedError)
    assert not isinstance(exc.value, specific)
    assert exc.value.status_code == 500


def test_401_raises_unauthorized_error():
    def handler(_request):
        return httpx.Response(
            401,
            json={"error": "unauthorized", "message": "HTTP Basic auth required."},
            headers={"WWW-Authenticate": "Basic realm=\"ops\""},
        )

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(UnauthorizedError):
        client.get_website("example.com")


def test_non_json_body_on_success_raises_agentdisco_error():
    def handler(_request):
        return httpx.Response(200, text="not json at all", headers={"Content-Type": "text/plain"})

    client = AgentDisco(transport=make_transport(handler))

    with pytest.raises(AgentDiscoError):
        client.get_website("example.com")


def test_context_manager_closes_session():
    handler_calls = 0

    def handler(_request):
        nonlocal handler_calls
        handler_calls += 1
        return httpx.Response(200, json={
            "host": "x.com",
            "latestGrade": "B",
            "latestScore": 80,
            "lastScannedAt": "2026-04-24T00:00:00+00:00",
            "scanCount": 1,
        })

    with AgentDisco(transport=make_transport(handler)) as client:
        client.get_website("x.com")

    assert handler_calls == 1
