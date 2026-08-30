"""SSRF protection tests.

These tests exist to stay hostile. If one fails after a change to
``app/security/url_validation.py``, the correct response is almost always to fix
the code, not to relax the test.
"""

from __future__ import annotations

import pytest

from app.core.errors import UnsafeURLError
from app.security.url_validation import (
    is_blocked_ip,
    normalize_hostname,
    parse_ip_literal,
    validate_resolved_ip,
    validate_url,
)


def _assert_rejected(url: str) -> UnsafeURLError:
    with pytest.raises(UnsafeURLError) as exc_info:
        validate_url(url)
    return exc_info.value


class TestSchemes:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "file://C:/Windows/win.ini",
            "gopher://example.com:70/_test",
            "ftp://example.com/file",
            "dict://example.com:2628/",
            "data:text/html,<script>alert(1)</script>",
            "javascript:alert(1)",
            "jar:http://example.com!/",
            "ldap://example.com",
            "netdoc:///etc/passwd",
        ],
    )
    def test_non_http_schemes_rejected(self, url: str) -> None:
        _assert_rejected(url)

    def test_http_and_https_allowed(self) -> None:
        assert validate_url("http://example.com/article").scheme == "http"
        assert validate_url("https://example.com/article").scheme == "https"


class TestLoopbackAndPrivate:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/",
            "http://localhost:80/admin",
            "http://LOCALHOST/",
            "http://localhost.localdomain/",
            "http://127.0.0.1/",
            "http://127.0.0.1:80/",
            "http://127.255.255.254/",
            "http://[::1]/",
            "http://0.0.0.0/",
            "http://10.0.0.1/",
            "http://10.255.255.255/",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.0.1/",
            "http://192.168.1.1/admin",
            "http://100.64.0.1/",
            "http://[fc00::1]/",
            "http://[fe80::1]/",
        ],
    )
    def test_private_destinations_rejected(self, url: str) -> None:
        _assert_rejected(url)

    def test_public_ip_literal_allowed(self) -> None:
        assert validate_url("http://93.184.216.34/").host == "93.184.216.34"


class TestCloudMetadata:
    """The highest-value SSRF target in any cloud deployment."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/",
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            "http://[fd00:ec2::254]/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://metadata/computeMetadata/v1/",
            "http://instance-data/latest/meta-data/",
            "http://169.254.170.2/v2/credentials/",
        ],
    )
    def test_metadata_endpoints_rejected(self, url: str) -> None:
        _assert_rejected(url)


class TestObfuscatedEncodings:
    """Loopback written in ways that defeat naive string comparison."""

    @pytest.mark.parametrize(
        ("literal", "expected"),
        [
            ("2130706433", "127.0.0.1"),  # decimal
            ("0x7f000001", "127.0.0.1"),  # hex
            ("127.1", "127.0.0.1"),  # short form
            ("127.0.1", "127.0.0.1"),  # three-part short form
            ("0177.0.0.1", "127.0.0.1"),  # octal first octet
            ("::ffff:127.0.0.1", "::ffff:7f00:1"),  # IPv4-mapped IPv6
        ],
    )
    def test_encodings_decode_to_loopback(self, literal: str, expected: str) -> None:
        parsed = parse_ip_literal(literal)
        assert parsed is not None, f"{literal} should parse as an IP literal"
        assert str(parsed) == expected
        blocked, _ = is_blocked_ip(parsed)
        assert blocked, f"{literal} decodes to loopback and must be blocked"

    @pytest.mark.parametrize(
        "url",
        [
            "http://2130706433/",
            "http://0x7f000001/",
            "http://127.1/",
            "http://0177.0.0.1/",
            "http://[::ffff:127.0.0.1]/",
            "http://[::ffff:169.254.169.254]/",
            "http://[0:0:0:0:0:ffff:7f00:1]/",
        ],
    )
    def test_obfuscated_urls_rejected(self, url: str) -> None:
        _assert_rejected(url)

    def test_ipv4_mapped_ipv6_unwrapped(self) -> None:
        """::ffff:127.0.0.1 must not pass by being nominally an IPv6 address."""
        parsed = parse_ip_literal("::ffff:127.0.0.1")
        assert parsed is not None
        blocked, reason = is_blocked_ip(parsed)
        assert blocked
        assert reason == "loopback"

    def test_domain_name_is_not_an_ip_literal(self) -> None:
        assert parse_ip_literal("example.com") is None
        assert parse_ip_literal("news.bbc.co.uk") is None


class TestParserConfusion:
    @pytest.mark.parametrize(
        "url",
        [
            "http://user:pass@evil.example/",
            "http://trusted.example.com@127.0.0.1/",
            "http://example.com\\@127.0.0.1/",
            "http://example.com\t/",
            "http://example.com\n/",
            "http://exam\rple.com/",
            "http://example.com%00.evil.example/",
        ],
    )
    def test_confusing_urls_rejected(self, url: str) -> None:
        _assert_rejected(url)

    def test_credentials_rejected_even_for_public_host(self) -> None:
        """Credentials mislead readers about the real destination."""
        error = _assert_rejected("http://admin:secret@example.com/")
        assert error.details["reason"] == "credentials_in_url"

    def test_bare_single_label_hostname_rejected(self) -> None:
        error = _assert_rejected("http://intranet/")
        assert error.details["reason"] == "bare_hostname"


class TestInternalHostnames:
    @pytest.mark.parametrize(
        "url",
        [
            "http://kubernetes.default.svc/",
            "http://kubernetes.default.svc.cluster.local/",
            "http://myservice.svc.cluster.local/",
            "http://host.docker.internal/",
            "http://db.internal/",
            "http://printer.local/",
            "http://app.localhost/",
            "http://server.intranet/",
            "http://foo.ec2.internal/",
        ],
    )
    def test_internal_hostnames_rejected(self, url: str) -> None:
        _assert_rejected(url)


class TestPorts:
    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com:22/",
            "http://example.com:3306/",
            "http://example.com:6379/",
            "http://example.com:5432/",
            "http://example.com:11211/",
            "http://example.com:8080/",
            "http://example.com:9000/",
        ],
    )
    def test_non_standard_ports_rejected(self, url: str) -> None:
        """Redis, Postgres, and friends are the point of most SSRF chains."""
        _assert_rejected(url)

    def test_standard_ports_allowed(self) -> None:
        assert validate_url("http://example.com:80/").port == 80
        assert validate_url("https://example.com:443/").port == 443

    def test_default_ports_inferred(self) -> None:
        assert validate_url("http://example.com/").port == 80
        assert validate_url("https://example.com/").port == 443


class TestHostnameNormalization:
    def test_case_and_trailing_dot_normalized(self) -> None:
        assert validate_url("http://EXAMPLE.COM./").host == "example.com"

    def test_unicode_homograph_punycoded_before_comparison(self) -> None:
        # A Cyrillic lookalike letter must not be confused with its ASCII twin.
        result = validate_url("http://ex\u0430mple.com/")
        assert result.host.startswith("xn--")
        assert result.host.isascii()

    def test_normalize_hostname_rejects_empty(self) -> None:
        with pytest.raises(UnsafeURLError):
            normalize_hostname("")


class TestResolvedIPValidation:
    """Guards the post-DNS and post-connect checks that defeat rebinding."""

    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "10.0.0.5",
            "172.16.31.9",
            "192.168.1.1",
            "169.254.169.254",
            "::1",
            "fe80::1",
            "fc00::1",
            "0.0.0.0",
            "224.0.0.1",
        ],
    )
    def test_private_resolved_ips_rejected(self, ip: str) -> None:
        with pytest.raises(UnsafeURLError):
            validate_resolved_ip(ip)

    @pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"])
    def test_public_resolved_ips_allowed(self, ip: str) -> None:
        validate_resolved_ip(ip)

    def test_garbage_rejected(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_resolved_ip("not-an-ip")


class TestMalformedInput:
    @pytest.mark.parametrize("url", ["", "   ", "not a url", "http://", "https://", "://example.com"])
    def test_malformed_rejected(self, url: str) -> None:
        _assert_rejected(url)

    def test_overlong_url_rejected(self) -> None:
        error = _assert_rejected("http://example.com/" + "a" * 3000)
        assert error.details["reason"] == "url_too_long"


class TestErrorDisclosure:
    def test_message_does_not_leak_internal_detail(self) -> None:
        """A prober must not learn which internal range they hit."""
        error = _assert_rejected("http://169.254.169.254/latest/meta-data/")
        assert "169.254" not in error.message
        assert "metadata" not in error.message.lower()
        # The specific reason is still available for our own logs.
        assert error.details["reason"]


class TestLegitimateURLs:
    """The protections must not break ordinary news URLs."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bbc.com/news/world-12345678",
            "https://apnews.com/article/some-slug-abc123",
            "https://www.prothomalo.com/bangladesh/article/xyz",
            "https://example.com/path?query=value&other=2#fragment",
            "https://sub.domain.example.co.uk/deep/path/here",
            "https://example.com/%E0%A6%AC%E0%A6%BE%E0%A6%82%E0%A6%B2%E0%A6%BE",
        ],
    )
    def test_public_urls_accepted(self, url: str) -> None:
        result = validate_url(url)
        assert result.scheme == "https"
        assert result.host
