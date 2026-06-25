"""The asynchronous Agent Disco client.

`AsyncAgentDisco` mirrors the synchronous `AgentDisco` method-for-method
over httpx's async client — same arguments, same return dataclasses, same
typed exceptions (shared via `agentdisco._response.parse_json`). Use it
from `asyncio` code or any concurrent runner.

    import asyncio
    from agentdisco import AsyncAgentDisco

    async def main():
        async with AsyncAgentDisco(token="ak_...") as client:
            scan = await client.submit_scan("https://example.com")
            print(scan.id, scan.status)

    asyncio.run(main())
"""

from __future__ import annotations

import httpx

from agentdisco._response import parse_json
from agentdisco.client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT
from agentdisco.models import ApiKey, Scan, Website

_USER_AGENT = "agentdisco-python-async/0.3.0"


class AsyncAgentDisco:
    """Asynchronous Agent Disco client. The async twin of `AgentDisco`.

    Construct once and reuse — httpx's async client is connection-pooled.
    Close it with `await client.aclose()`, or use it as an async context
    manager (`async with AsyncAgentDisco() as client: ...`).
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Construct a client. See `AgentDisco.__init__` for the arguments —
        they're identical (`transport` here is an async transport, used by
        the SDK's own tests to pin a `MockTransport`).
        """
        self._token = token
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
            transport=transport,
        )

    async def __aenter__(self) -> AsyncAgentDisco:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying async HTTP session. Safe to call twice."""
        await self._http.aclose()

    # -- Scans ----------------------------------------------------------

    async def submit_scan(self, url: str) -> Scan:
        """Queue a scan for `url`. See `AgentDisco.submit_scan`."""
        response = await self._http.post("/api/v1/scans", json={"url": url})
        return Scan.from_response(parse_json(response))

    async def get_scan(self, scan_id: str) -> Scan:
        """Fetch a scan by UUID. See `AgentDisco.get_scan`."""
        response = await self._http.get(f"/api/v1/scans/{scan_id}")
        return Scan.from_response(parse_json(response))

    # -- Websites -------------------------------------------------------

    async def get_website(self, host: str) -> Website:
        """Latest grade for a scanned host. See `AgentDisco.get_website`."""
        response = await self._http.get(f"/api/v1/websites/{host}")
        return Website.from_response(parse_json(response))

    async def get_scans(self, host: str, *, page: int = 1, per_page: int = 10) -> list[Scan]:
        """A page of a host's completed-scan history. See `AgentDisco.get_scans`."""
        response = await self._http.get(
            f"/api/v1/websites/{host}/scans",
            params={"page": page, "perPage": per_page},
        )
        payload = parse_json(response)
        return [Scan.from_response(s) for s in payload.get("scans", [])]

    async def rescan(self, host: str) -> Scan:
        """Queue a fresh scan of a known host. See `AgentDisco.rescan`."""
        response = await self._http.post(f"/api/v1/websites/{host}/rescan")
        return Scan.from_response(parse_json(response))

    # -- API keys -------------------------------------------------------

    async def mint_key(self) -> ApiKey:
        """Mint an anonymous-tier API key. See `AgentDisco.mint_key`."""
        response = await self._http.post("/api/v1/keys")
        return ApiKey.from_response(parse_json(response))

    # -- Colony agent login (RFC 8693) ----------------------------------

    async def exchange_colony_token(self, subject_token: str) -> ApiKey:
        """Exchange a Colony agent token for an API key. See
        `AgentDisco.exchange_colony_token`.
        """
        response = await self._http.post(
            "/api/v1/auth/colony/agent",
            json={"subject_token": subject_token},
        )
        return ApiKey.from_response(parse_json(response))

    @classmethod
    async def from_colony_token(
        cls,
        subject_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> AsyncAgentDisco:
        """Build an authenticated client from a Colony agent token. See
        `AgentDisco.from_colony_token`.
        """
        async with cls(base_url=base_url, timeout=timeout, transport=transport) as anon:
            key = await anon.exchange_colony_token(subject_token)
        return cls(token=key.token, base_url=base_url, timeout=timeout, transport=transport)
