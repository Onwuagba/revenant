"""Unit tests for urlguard.py (ingestion tasks 1-2)."""

import pytest
from revenant.compiler.urlguard import (
    UrlGuardError,
    check_redirect,
    check_url,
)


def _resolver_returning(ip: str):
    """Return a fake resolver function that always resolves to *ip*."""

    def resolver(host, port):
        return ip

    return resolver


class TestScheme:
    def test_https_allowed(self):
        t = check_url("https://example.com/path", resolver=_resolver_returning("93.184.216.34"))
        assert t.host == "example.com"
        assert t.ip == "93.184.216.34"

    def test_http_blocked_by_default(self):
        with pytest.raises(UrlGuardError) as exc:
            check_url("http://example.com", resolver=_resolver_returning("93.184.216.34"))
        assert exc.value.code == "HTTP_NOT_ALLOWED"

    def test_http_allowed_with_flag(self):
        """http is allowed with the flag, but loopback is still blocked by IP."""
        # Public IP via http with allow_http -> OK
        t = check_url(
            "http://example.com:8080",
            allow_http=True,
            resolver=_resolver_returning("93.184.216.34"),
        )
        assert t.port == 8080
        # Loopback is still blocked even with allow_http
        with pytest.raises(UrlGuardError):
            check_url(
                "http://localhost:8080", allow_http=True, resolver=_resolver_returning("127.0.0.1")
            )

    def test_ftp_blocked(self):
        with pytest.raises(UrlGuardError) as exc:
            check_url("ftp://example.com")
        assert exc.value.code == "BAD_SCHEME"

    def test_no_scheme_blocked(self):
        with pytest.raises(UrlGuardError):
            check_url("example.com/path")


class TestBlockedAddresses:
    @pytest.mark.parametrize(
        "ip,cidr_name",
        [
            ("127.0.0.1", "loopback"),
            ("127.1.2.3", "loopback"),
            ("10.0.0.1", "private-10"),
            ("10.255.255.255", "private-10"),
            ("172.16.0.1", "private-172"),
            ("172.31.255.255", "private-172"),
            ("192.168.1.1", "private-192"),
            ("169.254.1.1", "link-local"),
            ("169.254.169.254", "cloud-metadata"),
            ("0.0.0.0", "current-net"),
            ("100.64.0.1", "cgnat"),
            ("::1", "ipv6-loopback"),
            ("fc00::1", "ipv6-ula"),
            ("fe80::1", "ipv6-link-local"),
        ],
    )
    def test_blocked_ip_rejected(self, ip, cidr_name):
        with pytest.raises(UrlGuardError) as exc:
            check_url("https://evil.com", resolver=_resolver_returning(ip))
        assert exc.value.code == "BLOCKED_ADDRESS"

    def test_public_ip_allowed(self):
        t = check_url("https://example.com", resolver=_resolver_returning("93.184.216.34"))
        assert t.ip == "93.184.216.34"

    def test_ip_literal_blocked(self):
        with pytest.raises(UrlGuardError):
            check_url("https://127.0.0.1/")
        with pytest.raises(UrlGuardError):
            check_url("https://10.0.0.1/")
        with pytest.raises(UrlGuardError):
            check_url("https://169.254.169.254/")

    def test_ip_literal_allowed(self):
        t = check_url("https://93.184.216.34/")
        assert t.ip == "93.184.216.34"

    def test_metadata_hostname_blocked(self):
        with pytest.raises(UrlGuardError):
            check_url("https://metadata.google.internal/")


class TestRedirects:
    def test_redirect_rechecked(self):
        """Requirement 3.3: redirect to 127.0.0.1 is rejected."""
        current = check_url("https://example.com", resolver=_resolver_returning("93.184.216.34"))
        with pytest.raises(UrlGuardError):
            check_redirect(current, "https://evil.com", resolver=_resolver_returning("127.0.0.1"))

    def test_redirect_to_public_ok(self):
        current = check_url("https://example.com", resolver=_resolver_returning("93.184.216.34"))
        t = check_redirect(current, "https://other.com", resolver=_resolver_returning("8.8.8.8"))
        assert t.ip == "8.8.8.8"

    def test_too_many_redirects(self):
        current = check_url("https://example.com", resolver=_resolver_returning("93.184.216.34"))
        with pytest.raises(UrlGuardError) as exc:
            check_redirect(
                current,
                "https://other.com",
                hop=5,
                max_hops=5,
                resolver=_resolver_returning("8.8.8.8"),
            )
        assert exc.value.code == "TOO_MANY_REDIRECTS"


class TestResolvedTarget:
    def test_pinned_url(self):
        t = check_url("https://example.com/path?q=1", resolver=_resolver_returning("93.184.216.34"))
        pinned = t.pinned_url()
        assert "93.184.216.34" in pinned
        assert "/path" in pinned
