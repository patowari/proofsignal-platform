"""URL and IP address validation for SSRF protection.

This module answers one question: is this destination safe for our server to
connect to? It is pure and synchronous so it can be exhaustively unit tested;
the networking lives in safe_fetch.py.

Threat model and rationale: docs/SECURITY.md.

Do not weaken anything here to make a test or feature easier. If a test needs a
local server, scope an allowlist to that fixture rather than relaxing a rule.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.errors import UnsafeURLError

ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Networks we must never connect to on a user's behalf. Beyond the obvious
#: loopback and private ranges, 169.254.169.254 (cloud instance metadata) is the
#: highest-value SSRF target in any cloud deployment and lives in link-local.
_BLOCKED_IPV4 = (
    ipaddress.ip_network("0.0.0.0/8"),  # "this network"; 0.0.0.0 often reaches localhost
    ipaddress.ip_network("10.0.0.0/8"),  # RFC1918 private
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, includes cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918 private
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918 private
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved, includes broadcast
)

_BLOCKED_IPV6 = (
    ipaddress.ip_network("::/128"),  # unspecified
    ipaddress.ip_network("::1/128"),  # loopback
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local
    ipaddress.ip_network("ff00::/8"),  # multicast
    ipaddress.ip_network("2001:db8::/32"),  # documentation
)

#: Hostnames that resolve to internal infrastructure in container and
#: orchestrator environments. DNS checks catch most of these, but rejecting by
#: name too means we fail closed even where resolution behaves unexpectedly.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
        "instance-data.ec2.internal",
        "kubernetes",
        "kubernetes.default",
        "kubernetes.default.svc",
        "host.docker.internal",
        "gateway.docker.internal",
        "docker.for.mac.localhost",
    }
)

#: Suffixes covering internal service-discovery domains.
_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".localdomain",
    ".svc",
    ".svc.cluster.local",
    ".cluster.local",
    ".ec2.internal",
)

MAX_HOSTNAME_LENGTH = 253
MAX_URL_LENGTH = 2048


@dataclass(frozen=True, slots=True)
class ValidatedURL:
    """A URL that has passed structural validation.

    Structural validation only. The host has *not* yet been resolved or checked
    against blocked ranges -- that is validate_resolved_ip's job, and it must run
    again on every redirect hop.
    """

    url: str
    scheme: str
    host: str
    port: int
    is_literal_ip: bool


def _reject(reason: str, detail: str) -> UnsafeURLError:
    """Build a rejection.

    The user-facing message stays generic: telling a prober exactly which
    internal range they hit is free reconnaissance. The specific reason travels
    to the logs in ``details``.
    """
    return UnsafeURLError(
        "This URL cannot be fetched because it does not point to a publicly reachable address.",
        {"reason": reason, "detail": detail},
    )


def normalize_hostname(host: str) -> str:
    """Lowercase, strip the trailing dot, and IDNA-encode.

    Unicode homographs are folded to punycode *before* any comparison, so a
    lookalike hostname cannot slip past the blocklist by using a different script.
    """
    host = host.strip().rstrip(".").lower()
    if not host:
        raise _reject("empty_host", "hostname is empty")
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        # Not IDNA-encodable. Plain ASCII hosts (IP literals, hosts with
        # underscores) are fine; anything else is rejected.
        if not host.isascii():
            raise _reject("invalid_hostname", "hostname is not encodable") from None
    return host


def parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a host as an IP literal, including obfuscated encodings.

    Attackers write loopback many ways to defeat naive string checks:
    ``127.0.0.1``, ``127.1``, ``2130706433`` (decimal), ``0x7f000001`` (hex),
    ``0177.0.0.1`` (octal), ``[::ffff:127.0.0.1]`` (IPv4-mapped IPv6).
    ``ipaddress`` deliberately rejects most of these forms, so we decode them
    ourselves and return a real address object to be range-checked.

    Returns None when the host is a genuine domain name.
    """
    host = host.strip("[]")

    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass

    # Bare integer, e.g. 2130706433 == 127.0.0.1
    if host.isdigit():
        try:
            value = int(host)
        except ValueError:
            return None
        if 0 <= value <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(value)
        return None

    # Hex form, e.g. 0x7f000001
    if host.lower().startswith("0x"):
        try:
            value = int(host, 16)
        except ValueError:
            return None
        if 0 <= value <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(value)
        return None

    # Dotted forms with octal or hex parts, or fewer than four parts (127.1).
    parts = host.split(".")
    if not (1 < len(parts) <= 4) or not all(parts):
        return None

    try:
        values: list[int] = []
        for part in parts:
            if part.lower().startswith("0x"):
                values.append(int(part, 16))
            elif part.startswith("0") and len(part) > 1:
                values.append(int(part, 8))
            elif part.isdigit():
                values.append(int(part))
            else:
                return None

        # Short forms pack the final value into the remaining low octets:
        # 127.1 -> 127.0.0.1, 10.1.2 -> 10.1.0.2
        if len(values) < 4:
            last = values.pop()
            missing = 4 - len(values) - 1
            if last >= 256 ** (missing + 1):
                return None
            values.extend((last >> (8 * i)) & 0xFF for i in range(missing, -1, -1))

        if len(values) != 4 or any(v < 0 or v > 255 for v in values):
            return None
        return ipaddress.IPv4Address(".".join(str(v) for v in values))
    except (ValueError, ipaddress.AddressValueError):
        return None


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
    """Check an address against every blocked range. Returns (blocked, reason)."""
    # Unwrap IPv4-in-IPv6 forms first, or ::ffff:127.0.0.1 would sail past the
    # IPv4 loopback check by being nominally an IPv6 address.
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_blocked_ip(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            return is_blocked_ip(ip.sixtofour)
        if ip.teredo is not None:
            return is_blocked_ip(ip.teredo[1])

    # Library classifications first: they track registry changes we might miss.
    if ip.is_loopback:
        return True, "loopback"
    if ip.is_link_local:
        return True, "link_local"
    if ip.is_multicast:
        return True, "multicast"
    if ip.is_unspecified:
        return True, "unspecified"
    if ip.is_reserved:
        return True, "reserved"
    if ip.is_private:
        return True, "private"

    blocked_networks = _BLOCKED_IPV4 if isinstance(ip, ipaddress.IPv4Address) else _BLOCKED_IPV6
    for network in blocked_networks:
        if ip in network:
            return True, f"blocked_range:{network}"

    if not ip.is_global:
        return True, "not_globally_routable"

    return False, ""


def validate_resolved_ip(ip_str: str) -> None:
    """Validate an address we are about to connect to.

    Called after DNS resolution and again against the socket's actual peer
    address. That second call is what defeats DNS rebinding, where a hostname
    resolves to a public IP for our check and a private one for our connect.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        raise _reject("invalid_ip", f"not a valid IP address: {ip_str}") from None

    blocked, reason = is_blocked_ip(ip)
    if blocked:
        raise _reject("blocked_ip", f"{ip_str} is {reason}")


def validate_url(raw_url: str) -> ValidatedURL:
    """Structural validation, before any DNS resolution.

    Rejects bad schemes, embedded credentials, disallowed ports, internal
    hostnames, and IP literals in blocked ranges. Passing here does NOT mean the
    destination is safe -- the resolved address must still be checked.
    """
    if not raw_url or not raw_url.strip():
        raise _reject("empty_url", "URL is empty")

    raw_url = raw_url.strip()
    if len(raw_url) > MAX_URL_LENGTH:
        raise _reject("url_too_long", f"URL exceeds {MAX_URL_LENGTH} characters")

    # Control characters and whitespace inside a URL are used to make two
    # parsers disagree about where the host ends.
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw_url):
        raise _reject("control_characters", "URL contains control characters")

    # Backslashes are treated as slashes by some clients but not by urlsplit,
    # which is a classic way to smuggle a different host past validation.
    if "\\" in raw_url:
        raise _reject("backslash", "URL contains a backslash")

    try:
        parts = urlsplit(raw_url)
    except ValueError as exc:
        raise _reject("unparseable", f"URL could not be parsed: {exc}") from None

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise _reject("bad_scheme", f"scheme {scheme!r} is not allowed")

    # Credentials can mislead a human reader, and some parsers, about which host
    # is really being contacted: http://trusted.example.com@evil.example/
    if parts.username or parts.password:
        raise _reject("credentials_in_url", "URL must not contain credentials")

    if not parts.hostname:
        raise _reject("no_host", "URL has no host")

    host = normalize_hostname(parts.hostname)
    if len(host) > MAX_HOSTNAME_LENGTH:
        raise _reject("hostname_too_long", "hostname is too long")

    # A hostname must contain only DNS-legal characters. Percent-encoding in the
    # host is the danger case: parsers disagree about whether to decode it, so
    # "example.com%00.evil.example" can validate as one host and be connected to
    # as another. Reject anything outside the DNS alphabet rather than guessing.
    if not all(c.isalnum() or c in "-._" for c in host.replace(":", "")):
        raise _reject("invalid_hostname_chars", f"hostname {host!r} contains illegal characters")

    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise _reject("bad_port", "port is not a valid integer") from None

    settings = get_settings()
    if port not in settings.allowed_url_ports:
        raise _reject("blocked_port", f"port {port} is not allowed")

    # Reject internal names before resolution so we fail closed even if DNS
    # behaves unexpectedly.
    if host in _BLOCKED_HOSTNAMES:
        raise _reject("blocked_hostname", f"hostname {host!r} is internal")
    if any(host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES):
        raise _reject("blocked_hostname_suffix", f"hostname {host!r} is internal")

    literal_ip = parse_ip_literal(host)

    # A bare single-label host ("intranet") is an internal name by definition;
    # a real public destination always has a dot. IP literals are exempt.
    if literal_ip is None and "." not in host:
        raise _reject("bare_hostname", f"hostname {host!r} has no public domain")

    if literal_ip is not None:
        blocked, reason = is_blocked_ip(literal_ip)
        if blocked:
            raise _reject("blocked_ip_literal", f"{host} is {reason}")
        # Normalize obfuscated literals so downstream code and logs agree on
        # what we actually contacted.
        host = str(literal_ip)

    return ValidatedURL(
        url=raw_url,
        scheme=scheme,
        host=host,
        port=port,
        is_literal_ip=literal_ip is not None,
    )
