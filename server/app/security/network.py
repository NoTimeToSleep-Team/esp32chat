from __future__ import annotations

from fastapi import Request


def resolve_client_ip(request: Request) -> str:
    """Return the socket peer address.

    ``X-Forwarded-For`` is deliberately ignored here: the app may be exposed
    directly, and a client-controlled header must never define rate-limit,
    brute-force or audit identities.  If a trusted reverse proxy is added in
    front of the server, configure it in uvicorn (``--forwarded-allow-ips``)
    instead of trusting the header in application code.
    """
    client = request.client
    if client and client.host:
        return client.host
    return "unknown"
