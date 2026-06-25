"""Async client tests.

Same MockTransport approach as the sync suite (the handler is a plain
sync callable; httpx's MockTransport adapts it for the async path), driven
through `asyncio.run` so no pytest-asyncio plugin is needed.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from agentdisco import AsyncAgentDisco, NotFoundError


def make_transport(handler):
    return httpx.MockTransport(handler)


def run(coro):
    return asyncio.run(coro)


def test_async_submit_scan_returns_scan():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/scans"
        assert json.loads(request.content) == {"url": "https://example.com"}
        return httpx.Response(202, json={
            "id": "019d0000-0000-7000-8000-000000000001",
            "status": "queued",
            "statusUrl": "/api/v1/scans/019d0000-0000-7000-8000-000000000001",
            "resultUrl": "/report/example.com",
            "grade": None,
            "score": None,
        })

    async def go():
        async with AsyncAgentDisco(transport=make_transport(handler)) as client:
            return await client.submit_scan("https://example.com")

    scan = run(go())
    assert scan.status == "queued"


def test_async_get_scans_returns_history():
    def handler(request):
        assert request.url.path == "/api/v1/websites/example.com/scans"
        return httpx.Response(200, json={
            "host": "example.com",
            "scans": [
                {
                    "id": "1", "status": "completed", "grade": "A", "score": 90,
                    "completedAt": "2026-06-25T10:00:00+00:00", "statusUrl": "/api/v1/scans/1",
                },
                {
                    "id": "2", "status": "completed", "grade": "B", "score": 70,
                    "completedAt": "2026-06-25T09:00:00+00:00", "statusUrl": "/api/v1/scans/2",
                },
            ],
            "totalCount": 2, "page": 1, "perPage": 10,
        })

    async def go():
        async with AsyncAgentDisco(transport=make_transport(handler)) as client:
            return await client.get_scans("example.com")

    scans = run(go())
    assert [s.grade for s in scans] == ["A", "B"]


def test_async_rescan_returns_queued_scan():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/websites/example.com/rescan"
        return httpx.Response(202, json={
            "id": "r", "status": "queued", "statusUrl": "/api/v1/scans/r",
            "resultUrl": "/report/example.com", "grade": None, "score": None,
        })

    async def go():
        async with AsyncAgentDisco(transport=make_transport(handler)) as client:
            return await client.rescan("example.com")

    assert run(go()).status == "queued"


def test_async_from_colony_token_returns_authed_client():
    minted = "ak_asyncmintedfromcolonytokenabcdefghijklmno"

    def handler(request):
        if request.url.path == "/api/v1/auth/colony/agent":
            return httpx.Response(201, json={
                "id": "k", "token": minted, "tokenPrefix": "ak_async",
                "rateLimitTier": "authenticated", "createdAt": "2026-06-25T10:00:00+00:00",
            })
        assert request.headers.get("Authorization") == f"Bearer {minted}"
        return httpx.Response(202, json={
            "id": "s", "status": "queued", "statusUrl": "/api/v1/scans/s",
            "resultUrl": "/report/example.com", "grade": None, "score": None,
        })

    async def go():
        client = await AsyncAgentDisco.from_colony_token(
            "colony-jwt", transport=make_transport(handler),
        )
        try:
            return await client.submit_scan("https://example.com")
        finally:
            await client.aclose()

    assert run(go()).status == "queued"


def test_async_404_raises_not_found():
    def handler(_request):
        return httpx.Response(404, json={"error": "not_found", "message": "nope"})

    async def go():
        async with AsyncAgentDisco(transport=make_transport(handler)) as client:
            await client.get_website("nobody.example")

    with pytest.raises(NotFoundError):
        run(go())
