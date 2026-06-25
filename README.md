# agentdisco — Python client for Agent Disco

[![PyPI version](https://img.shields.io/pypi/v/agentdisco.svg)](https://pypi.org/project/agentdisco/)
[![Python versions](https://img.shields.io/pypi/pyversions/agentdisco.svg)](https://pypi.org/project/agentdisco/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/agentdisco/agentdisco-python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/agentdisco/agentdisco-python-sdk/actions/workflows/ci.yml)

Grade any public URL for AI-agent discoverability. Thin Python wrapper
over the REST API at <https://agentdisco.io/api/v1>.

## Install

```bash
pip install agentdisco
```

Requires Python 3.9+.

## Quick start

### Submit a scan (anonymous, 10 scans/day/IP)

```python
from agentdisco import AgentDisco

with AgentDisco() as client:
    scan = client.submit_scan("https://example.com")
    print(scan.id, scan.status)
```

### Poll until complete

```python
import time

with AgentDisco() as client:
    scan = client.submit_scan("https://example.com")
    while scan.status not in {"completed", "failed"}:
        time.sleep(5)
        scan = client.get_scan(scan.id)

    print(f"grade: {scan.grade} ({scan.score}/100)")
```

### Mint a key (raises your quota to 100 scans/day)

```python
from agentdisco import AgentDisco

# Unauthenticated mint — no prior token needed, rate-limited at
# 5 keys/hour/IP. Token is shown ONCE; store it.
key = AgentDisco().mint_key()
print(key.token)  # ak_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

authed = AgentDisco(token=key.token)
authed.submit_scan("https://your-site.example")
```

### Get summary for a previously-scanned host

```python
with AgentDisco() as client:
    site = client.get_website("example.com")
    print(site.latest_grade, site.latest_score, site.scan_count)
```

### Scan history + re-scan

```python
with AgentDisco() as client:
    # Paginated history, most-recent first (per_page capped at 50).
    for scan in client.get_scans("example.com", per_page=20):
        print(scan.grade, scan.score)

    # Queue a fresh scan of a known host (counts against your scan quota).
    fresh = client.rescan("example.com")
    print(fresh.id, fresh.status)
```

### Async client

`AsyncAgentDisco` mirrors `AgentDisco` method-for-method over `asyncio`:

```python
import asyncio
from agentdisco import AsyncAgentDisco

async def main():
    async with AsyncAgentDisco(token="ak_...") as client:
        scan = await client.submit_scan("https://example.com")
        history = await client.get_scans("example.com")
        print(scan.id, len(history))

asyncio.run(main())
```

Same arguments, return types, and exceptions as the sync client —
including `await AsyncAgentDisco.from_colony_token(...)`.

### Sign in with the Colony (agents)

Autonomous agents on [The Colony](https://thecolony.cc) can authenticate
without a browser. Exchange your Colony agent token for an
authenticated-tier Agent Disco key — OAuth 2.0 Token Exchange (RFC 8693),
no redirect:

```python
from agentdisco import AgentDisco

# One-liner: exchange a Colony agent token and get an authed client.
client = AgentDisco.from_colony_token(my_colony_token)
client.submit_scan("https://your-site.example")     # authenticated tier (500/day)

# Or keep the minted key's plaintext to reuse across processes:
key = AgentDisco().exchange_colony_token(my_colony_token)
print(key.token, key.rate_limit_tier)                # ak_…  authenticated
```

Agent-only: a human Colony subject is rejected with `UnauthorizedError`.

## Higher rate limits

Authenticated-tier keys (500 scans/day/key) need a signed-in account,
or a Colony agent login (above).
Sign up at <https://agentdisco.io/register>, then mint via the web
form at <https://agentdisco.io/developers>.

| Tier | Rate limit | How to get |
|---|---|---|
| Anonymous (no key) | 10 scans / day / IP | default |
| Anonymous key | 100 scans / day / key | `mint_key()` above |
| Authenticated key | 500 scans / day / key | sign in (`/developers`) or `from_colony_token()` |

## Error handling

```python
from agentdisco import (
    AgentDisco,
    InvalidUrlError,
    NotFoundError,
    RateLimitedError,
)

try:
    scan = AgentDisco().submit_scan("https://example.com")
except InvalidUrlError as e:
    print(f"URL rejected: {e}")
except RateLimitedError as e:
    print(f"quota exceeded; retry in {e.retry_after_seconds}s")
except NotFoundError as e:
    print(f"not found: {e}")
```

All SDK-raised exceptions inherit from `AgentDiscoError`, so a single
broad catch works too:

```python
from agentdisco import AgentDiscoError
try:
    ...
except AgentDiscoError as e:
    log.warning("agentdisco failure: %s", e)
```

Network-layer failures (connection timeout, DNS) leak through as raw
`httpx.HTTPError` — they're platform issues, not API errors.

## Custom base URL

For self-hosted deployments or local testing:

```python
AgentDisco(base_url="http://localhost:1977")
```

## Links

- API docs: <https://agentdisco.io/api/docs>
- Check catalogue: <https://agentdisco.io/checks>
- Live scanner: <https://agentdisco.io>

## Licence

MIT. See [`LICENSE`](LICENSE). The scanner itself is operated by
**Starsol Ltd** (England, company 06002018); only this client library
is open-source. Issues + pull requests welcome.
