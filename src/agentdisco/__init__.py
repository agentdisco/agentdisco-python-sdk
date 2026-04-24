"""Agent Disco Python client.

Grade any public URL for AI-agent discoverability. Wraps the REST API
at https://agentdisco.io/api/v1.

Basic usage:

    >>> from agentdisco import AgentDisco
    >>> client = AgentDisco()                        # anonymous (10 scans/day/IP)
    >>> scan = client.submit_scan("https://example.com")
    >>> scan.id                                      # UUID
    >>> client.get_scan(scan.id).status              # poll: queued/running/completed
    >>> client.get_website("example.com").grade      # summary: A..F

With a key (100 or 500 scans/day depending on tier):

    >>> key = AgentDisco().mint_key()
    >>> print(key.token)                             # store this — shown once
    >>> authed = AgentDisco(token=key.token)
    >>> authed.submit_scan("https://example.com")

See https://agentdisco.io/api/docs for the full OpenAPI spec.
"""

from agentdisco.client import AgentDisco
from agentdisco.exceptions import (
    AgentDiscoError,
    ApiError,
    InvalidUrlError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
)
from agentdisco.models import ApiKey, Scan, Website

__all__ = [
    "AgentDisco",
    "AgentDiscoError",
    "ApiError",
    "ApiKey",
    "InvalidUrlError",
    "NotFoundError",
    "RateLimitedError",
    "Scan",
    "UnauthorizedError",
    "Website",
]

__version__ = "0.1.0"
