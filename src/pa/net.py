"""Privacy-hardened HTTP client used by every outbound web tool.

Design goals:
- No environment-driven proxy or auth (trust_env=False) so a stray HTTP_PROXY
  can't silently relay our traffic.
- No cookie jar — every request is anonymous and stateless.
- No Referer header (httpx doesn't auto-add one; we just don't set it).
- Reject schemes other than http/https.
- Reject hosts that resolve to private / loopback / link-local addresses, so
  a malicious URL handed to the model can't be used to scan our LAN or hit
  the agent's own local services.
- Cap response size to bound memory and context.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Final
from urllib.parse import urlsplit

import httpx

from pa.config import settings

log = logging.getLogger(__name__)

_ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})
_USER_AGENT: Final[str] = "Mozilla/5.0 (compatible; pa-agent/0.1)"
_DEFAULT_HEADERS: Final[dict[str, str]] = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}


class UnsafeURLError(ValueError):
    """Raised when a URL fails the safety checks before we send a request."""


def _is_private_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url(url: str) -> str:
    """Return the URL if it's safe to fetch; raise UnsafeURLError otherwise.

    "Safe" here means: http(s) only, host is a public IP or resolves to one.
    The check is best-effort against accidental leaks — not a defense against
    a determined attacker who controls DNS.
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError("empty url")
    parsed = urlsplit(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("url has no host")

    host = parsed.hostname
    # Literal IP — check directly.
    try:
        ipaddress.ip_address(host)
        if _is_private_address(host):
            raise UnsafeURLError(f"refusing to fetch private address: {host}")
        return url
    except ValueError:
        pass

    # Hostname — resolve and check every answer.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"dns lookup failed for {host}: {exc}") from exc
    for info in infos:
        sockaddr = info[4]
        addr = sockaddr[0]
        if _is_private_address(addr):
            raise UnsafeURLError(
                f"refusing to fetch {host}: resolves to private address {addr}"
            )
    return url


def build_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Construct a fresh async client. Caller is responsible for closing it."""
    return httpx.AsyncClient(
        trust_env=False,
        cookies=None,
        headers=_DEFAULT_HEADERS,
        follow_redirects=True,
        max_redirects=5,
        timeout=httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=timeout),
    )


async def safe_get(url: str, *, timeout: float = 30.0) -> httpx.Response:
    """GET a URL with the hardened client; validates URL first and caps size."""
    safe = validate_url(url)
    max_bytes = settings.web_max_fetch_bytes
    async with build_client(timeout=timeout) as client, client.stream("GET", safe) as response:
        response.raise_for_status()
        # Check the final URL again — redirects could have landed somewhere private.
        final = str(response.url)
        if final != safe:
            validate_url(final)
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise UnsafeURLError(f"response exceeded {max_bytes} bytes; aborting")
            chunks.append(chunk)
        # Build a synthetic response object carrying the body we collected.
        response._content = b"".join(chunks)  # noqa: SLF001
        return response
