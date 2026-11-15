"""URL guard (SSRF policy).

Checks that a URL is safe to fetch: https-only (by default), DNS resolves to
a public address (not private/loopback/link-local/cloud-metadata), with size
and time caps. Redirects are re-checked on every hop.

Source: ingestion requirements 3.1–3.4, ``docs/SECURITY.md`` T6/T7/T9.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


class UrlGuardError(Exception):
    """Raised when a URL fails the SSRF guard."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True)
class ResolvedTarget:
    """A URL that passed the guard, with the resolved IP pinned."""

    url: str
    host: str
    ip: str
    port: int

    def pinned_url(self, scheme: str | None = None) -> str:
        """Return the URL with the host replaced by the pinned IP.

        This prevents DNS rebinding between the check and the connect.
        """
        parsed = urlparse(self.url)
        sch = scheme or parsed.scheme
        return f"{sch}://{self.ip}:{self.port}{parsed.path}" + (
            f"?{parsed.query}" if parsed.query else ""
        )


# ---------------------------------------------------------------------------
# Blocked address ranges
# ---------------------------------------------------------------------------
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # Loopback
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    # Private
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    # Link-local
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    # Current network
    ipaddress.ip_network("0.0.0.0/8"),
    # CGNAT
    ipaddress.ip_network("100.64.0.0/10"),
    # Cloud metadata endpoints (AWS/Azure/GCP)
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("fd00:ec::/48"),  # GCP metadata
    # IPv6 unspecified
    ipaddress.ip_network("::/128"),
    # IPv4-mapped IPv6 loopback
    ipaddress.ip_network("::ffff:127.0.0.0/104"),
]

#: Cloud metadata hostnames to block even before DNS.
_BLOCKED_HOSTS: frozenset[str] = frozenset({
    "metadata.google.internal",
    "169.254.169.254",
    "metadata.aws.internal",
})


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True if *ip_str* falls in any blocked range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable -> block
    for net in _BLOCKED_NETWORKS:
        if addr in net:
            return True
    return False


def _resolve_host(host: str, port: int) -> str:
    """Resolve *host* to an IP address via DNS. Returns the first A/AAAA record."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlGuardError("DNS_RESOLVE_FAILED", f"Cannot resolve {host}: {exc}") from exc
    for family, _type, _proto, _canon, sockaddr in infos:
        ip = sockaddr[0]
        return ip
    raise UrlGuardError("DNS_RESOLVE_FAILED", f"No address records for {host}")


def check_url(
    url: str,
    *,
    allow_http: bool = False,
    resolver: Any = None,
) -> ResolvedTarget:
    """Validate that *url* is safe to fetch.

    - https only (unless *allow_http* for local testing)
    - host not in blocked hostnames
    - DNS resolves to a public address
    - returns ResolvedTarget with the pinned IP

    Raises :class:`UrlGuardError` on any check failure.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme not in ("https", "http"):
        raise UrlGuardError("BAD_SCHEME", f"Only https/http allowed, got {scheme!r}")
    if scheme == "http" and not allow_http:
        raise UrlGuardError("HTTP_NOT_ALLOWED", "https required; http blocked")

    host = parsed.hostname or ""
    if not host:
        raise UrlGuardError("NO_HOST", "URL has no hostname")

    if host.lower() in _BLOCKED_HOSTS:
        raise UrlGuardError("BLOCKED_HOST", f"Host {host} is blocked (metadata endpoint)")

    port = parsed.port or (443 if scheme == "https" else 80)

    # If the host is already an IP literal, check it directly.
    try:
        ipaddress.ip_address(host)
        ip = host
    except ValueError:
        resolve_fn = resolver or _resolve_host
        ip = resolve_fn(host, port)

    if _is_blocked_ip(ip):
        raise UrlGuardError(
            "BLOCKED_ADDRESS",
            f"Resolved address {ip} for {host} is in a blocked range",
        )

    return ResolvedTarget(url=url, host=host, ip=ip, port=port)


def check_redirect(
    current: ResolvedTarget,
    next_url: str,
    *,
    allow_http: bool = False,
    resolver: Any = None,
    hop: int = 1,
    max_hops: int = 5,
) -> ResolvedTarget:
    """Re-check the guard on a redirect target. Caps the number of hops."""
    if hop >= max_hops:
        raise UrlGuardError("TOO_MANY_REDIRECTS", f"Exceeded {max_hops} redirect hops")
    return check_url(next_url, allow_http=allow_http, resolver=resolver)


# ---------------------------------------------------------------------------
# Defaults for guarded fetch
# ---------------------------------------------------------------------------
DEFAULT_MAX_SIZE = 2 * 1024 * 1024  # 2 MB
DEFAULT_TIMEOUT = 10.0  # seconds
DEFAULT_MAX_HOPS = 5
