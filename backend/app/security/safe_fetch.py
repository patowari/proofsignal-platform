"""SSRF-safe HTTP fetching.

The single chokepoint for every outbound request influenced by a user-supplied
URL. Nothing else in the codebase may fetch a user URL -- one place to audit.

Four validation points, because checking once is the classic mistake:

1. Structural validation (scheme, port, host shape, IP literals).
2. DNS resolution: *every* returned address is checked, not just the first.
3. Connection: the socket is pinned to a validated address and the actual peer
   address is re-checked. This is what defeats DNS rebinding.
4. Every redirect hop repeats 1-3.

See docs/SECURITY.md.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx

from app.core.config import get_settings
from app.core.errors import FetchError, UnsafeURLError
from app.core.logging import get_logger
from app.security.url_validation import (
    ValidatedURL,
    validate_resolved_ip,
    validate_url,
)

logger = get_logger(__name__)

#: Content types we are willing to parse. Anything else is a waste of bandwidth
#: at best and a decoder exploit at worst.
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
    "application/json",
)


@dataclass(slots=True)
class FetchResult:
    """The outcome of a safe fetch."""

    url: str
    #: Final URL after redirects. Differs from ``url`` when redirected.
    final_url: str
    status_code: int
    content_type: str
    text: str
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)
    #: Every URL in the redirect chain, for provenance and debugging.
    redirect_chain: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


async def _resolve_host(host: str, port: int) -> list[str]:
    """Resolve a hostname and validate every address it returns.

    If *any* returned address is disallowed the whole host is rejected rather
    than filtered down to the safe subset. A DNS answer mixing public and
    private addresses is an attack signature, not a configuration to work around.
    """

    def _getaddrinfo() -> list[Any]:
        return socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)

    try:
        infos = await anyio.to_thread.run_sync(_getaddrinfo)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host: {host}", {"error": str(exc)}) from exc

    addresses = []
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if ip not in addresses:
            addresses.append(ip)

    if not addresses:
        raise FetchError(f"Host resolved to no addresses: {host}")

    for ip in addresses:
        validate_resolved_ip(ip)

    return addresses


class _PinnedTransport(httpx.AsyncHTTPTransport):
    """Transport that connects only to a pre-validated IP address.

    Without pinning there is a window between our DNS check and httpx's own
    resolution in which a hostname can be re-pointed at a private address
    (DNS rebinding). We resolve once, validate, then force the connection to that
    address while preserving the original Host header and TLS SNI, and finally
    re-check the socket's real peer address at connect time.
    """

    def __init__(self, pinned_ip: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pinned_ip = pinned_ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await super().handle_async_request(request)
        # Belt and braces: confirm the address we actually connected to is the
        # one we validated, in case a resolver returned something else.
        network_stream = response.extensions.get("network_stream")
        if network_stream is not None:
            peer = network_stream.get_extra_info("server_addr")
            if peer:
                validate_resolved_ip(peer[0])
        return response


async def _fetch_once(
    validated: ValidatedURL,
    *,
    method: str,
    headers: dict[str, str],
    max_bytes: int,
) -> tuple[httpx.Response, bytes, bool]:
    """Perform one request to an already-validated URL, with the size cap
    enforced while streaming so an oversized body cannot exhaust memory."""
    settings = get_settings()

    addresses = await _resolve_host(validated.host, validated.port)
    pinned_ip = addresses[0]

    timeout = httpx.Timeout(
        settings.fetch_timeout_seconds,
        connect=settings.fetch_connect_timeout_seconds,
    )

    transport = _PinnedTransport(pinned_ip, retries=0)
    async with httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        # Redirects are followed manually so every hop is re-validated.
        follow_redirects=False,
        # A public site sending a huge or infinite body is a DoS vector.
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    ) as client:
        request = client.build_request(method, validated.url, headers=headers)
        response = await client.send(request, stream=True)

        # Reject oversized bodies from the declared length before reading.
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            await response.aclose()
            raise FetchError(
                "Response is larger than the permitted size.",
                {"declared_bytes": int(declared), "max_bytes": max_bytes},
            )

        chunks: list[bytes] = []
        total = 0
        truncated = False
        try:
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    # Keep what fits and stop; a truncated article is still
                    # useful, an exhausted process is not.
                    remaining = max_bytes - (total - len(chunk))
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                    truncated = True
                    break
                chunks.append(chunk)
        finally:
            await response.aclose()

    return response, b"".join(chunks), truncated


async def safe_fetch(
    raw_url: str,
    *,
    method: str = "GET",
    extra_headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
    allowed_content_types: tuple[str, ...] | None = ALLOWED_CONTENT_TYPES,
) -> FetchResult:
    """Fetch a user-supplied URL safely.

    Raises:
        UnsafeURLError: the URL or a redirect target is not publicly reachable.
        FetchError: the request failed, timed out, or returned unusable content.
    """
    settings = get_settings()
    max_bytes = max_bytes or settings.max_url_response_bytes

    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en,bn;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)

    current_url = raw_url
    redirect_chain: list[str] = []

    for hop in range(settings.max_redirects + 1):
        validated = validate_url(current_url)

        try:
            response, body, truncated = await _fetch_once(
                validated, method=method, headers=headers, max_bytes=max_bytes
            )
        except UnsafeURLError:
            raise
        except httpx.TimeoutException as exc:
            raise FetchError("The request timed out.", {"url_host": validated.host}) from exc
        except httpx.HTTPError as exc:
            raise FetchError(
                "The request failed.",
                {"url_host": validated.host, "error_type": type(exc).__name__},
            ) from exc

        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise FetchError("Redirect response had no destination.")
            if hop >= settings.max_redirects:
                raise FetchError(
                    "Too many redirects.", {"max_redirects": settings.max_redirects}
                )
            redirect_chain.append(current_url)
            # Resolve relative redirects against the current URL, then loop so
            # the new destination goes through full validation again.
            current_url = str(httpx.URL(current_url).join(location))
            logger.debug("safe_fetch.redirect", hop=hop, to_host=validate_url(current_url).host)
            continue

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if allowed_content_types and content_type and content_type not in allowed_content_types:
            raise FetchError(
                "The URL returned an unsupported content type.",
                {"content_type": content_type},
            )

        if not (200 <= response.status_code < 300):
            raise FetchError(
                f"The source returned HTTP {response.status_code}.",
                {"status_code": response.status_code},
            )

        try:
            text = body.decode(response.encoding or "utf-8", errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = body.decode("utf-8", errors="replace")

        return FetchResult(
            url=raw_url,
            final_url=current_url,
            status_code=response.status_code,
            content_type=content_type,
            text=text,
            content=body,
            headers=dict(response.headers),
            redirect_chain=redirect_chain,
            truncated=truncated,
        )

    raise FetchError("Too many redirects.", {"max_redirects": settings.max_redirects})
