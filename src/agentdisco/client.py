"""The AgentDisco client.

Thin wrapper over the REST API. Callers construct an `AgentDisco`
instance (with optional bearer token), then call methods that map
1:1 to endpoints and return dataclasses.

Scope is deliberately narrow — 4 endpoints today. More surface (report
diffs, check catalogue listing, scan history) can layer on without
breaking the existing shape.
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
from agentdisco.models import ApiKey, Scan, Website

DEFAULT_BASE_URL = "https://agentdisco.io"
DEFAULT_TIMEOUT = 30.0
_USER_AGENT = "agentdisco-python/0.2.0"


class AgentDisco:
    """Synchronous Agent Disco client.

    Construct once, reuse across calls — httpx's client is
    connection-pooled, so per-call construction would reopen TLS on
    every request.

    An async variant (`AsyncAgentDisco`) can follow when a caller needs
    one; today the synchronous API is enough for CI runners, CLIs,
    notebooks.

    Example:

        client = AgentDisco(token="ak_...")
        scan = client.submit_scan("https://example.com")
        while scan.status not in {"completed", "failed"}:
            time.sleep(5)
            scan = client.get_scan(scan.id)
        print(scan.grade)
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Construct a client.

        `token` is an API key obtained via `mint_key()` or the web
        flow at `/developers`. Absent → anonymous-tier rate limits.

        `base_url` defaults to prod. Override for self-hosted
        deployments or tests.

        `transport` is an httpx transport escape-hatch used by the
        SDK's own tests to pin a `MockTransport`. Real callers
        shouldn't need it.
        """
        self._token = token
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
            transport=transport,
        )

    def __enter__(self) -> AgentDisco:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session. Safe to call twice."""
        self._http.close()

    # -------------------------------------------------------------
    # Scans
    # -------------------------------------------------------------

    def submit_scan(self, url: str) -> Scan:
        """Queue a scan for `url`. Returns a Scan with status=queued.

        Raises `InvalidUrlError` if the URL fails server-side validation
        (wrong scheme, private IP, malformed, etc.). Raises
        `RateLimitedError` when the daily quota is used up — check
        `.retry_after_seconds` for when to retry.
        """
        response = self._http.post("/api/v1/scans", json={"url": url})
        payload = self._parse(response)
        return Scan.from_response(payload)

    def get_scan(self, scan_id: str) -> Scan:
        """Fetch a scan by UUID. Raises `NotFoundError` on unknown id."""
        response = self._http.get(f"/api/v1/scans/{scan_id}")
        payload = self._parse(response)
        return Scan.from_response(payload)

    # -------------------------------------------------------------
    # Websites
    # -------------------------------------------------------------

    def get_website(self, host: str) -> Website:
        """Latest grade + scan count for a host that's been scanned.

        Raises `NotFoundError` if the host has never been scanned (or
        has been unlisted — the API returns 404 for both, deliberately).
        """
        response = self._http.get(f"/api/v1/websites/{host}")
        payload = self._parse(response)
        return Website.from_response(payload)

    # -------------------------------------------------------------
    # API keys
    # -------------------------------------------------------------

    def mint_key(self) -> ApiKey:
        """Mint a new anonymous-tier API key.

        The response contains the plaintext token exactly once — store
        it immediately. The server keeps only a SHA-256 hash and
        cannot reconstruct the plaintext if you lose it.

        This method works without authentication (no token needed on
        the calling client). To mint an authenticated-tier key (500
        scans/day vs 100), sign in via the web flow at /developers.

        Rate-limited at 5 keys/hour/IP; burst-hammering trips
        `RateLimitedError`.
        """
        response = self._http.post("/api/v1/keys")
        payload = self._parse(response)
        return ApiKey.from_response(payload)

    # -------------------------------------------------------------
    # Colony agent login (OAuth 2.0 Token Exchange, RFC 8693)
    # -------------------------------------------------------------

    def exchange_colony_token(self, subject_token: str) -> ApiKey:
        """Exchange a Colony agent token for an Agent Disco API key.

        Non-interactive sign-in for autonomous agents on The Colony
        (https://thecolony.cc): present your Colony agent access token as
        `subject_token` and receive a freshly-minted, authenticated-tier
        (500 scans/day) Agent Disco API key bound to your Colony identity.
        The returned `ApiKey.token` is the plaintext — shown ONCE.

        No bearer token is needed on the calling client; the
        `subject_token` is the credential. Agent-only: a human Colony
        subject is rejected with `UnauthorizedError`. Raises
        `NotFoundError` if Colony login isn't enabled on the deployment.
        """
        response = self._http.post(
            "/api/v1/auth/colony/agent",
            json={"subject_token": subject_token},
        )
        payload = self._parse(response)
        return ApiKey.from_response(payload)

    @classmethod
    def from_colony_token(
        cls,
        subject_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> AgentDisco:
        """Build an authenticated client from a Colony agent token.

        One-liner for Colony agents: exchanges `subject_token` for an
        Agent Disco API key (see `exchange_colony_token`) and returns a
        client already authenticated with it.

            client = AgentDisco.from_colony_token(my_colony_token)
            client.submit_scan("https://example.com")

        To keep the minted key's plaintext (e.g. to persist + reuse across
        processes), call `exchange_colony_token` directly and read `.token`
        instead.
        """
        with cls(base_url=base_url, timeout=timeout, transport=transport) as anon:
            key = anon.exchange_colony_token(subject_token)
        return cls(token=key.token, base_url=base_url, timeout=timeout, transport=transport)

    # -------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        """Extract JSON body; raise the right exception on 4xx/5xx.

        Returns the raw dict — each caller wraps in its dataclass.
        """
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

        # Best-effort body parse so the error carries the server's
        # error code + message; don't fail the wrap if the body isn't
        # JSON (it usually is for /api/v1 but some 5xx paths return
        # plain text).
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
