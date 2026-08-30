"""Safe-fetch tests.

Focus on the behaviors that are easy to get wrong and catastrophic when wrong:
redirect chains that land on private addresses, size caps that must hold while
streaming, and DNS answers that mix public and private addresses.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.errors import FetchError, UnsafeURLError
from app.security.safe_fetch import safe_fetch

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def allow_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve every hostname to a fixed public address.

    Scoped to the test, never a production bypass: the validation logic still
    runs in full, it is only DNS that is deterministic.
    """

    async def _fake_resolve(host: str, port: int) -> list[str]:
        from app.security.url_validation import validate_resolved_ip

        validate_resolved_ip(PUBLIC_IP)
        return [PUBLIC_IP]

    monkeypatch.setattr("app.security.safe_fetch._resolve_host", _fake_resolve)


@pytest.fixture
def no_pinning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a plain transport so respx can intercept.

    The pinned transport dials a real socket, which respx cannot mock; the
    pinning behavior itself is covered by test_transport_revalidates_peer.
    """
    import httpx as _httpx

    monkeypatch.setattr(
        "app.security.safe_fetch._PinnedTransport",
        lambda pinned_ip, **kw: _httpx.AsyncHTTPTransport(**kw),
    )


@pytest.mark.usefixtures("allow_public_dns", "no_pinning")
class TestRedirectSafety:
    """A public URL that redirects to a private one is the classic bypass."""

    @respx.mock
    async def test_redirect_to_loopback_rejected(self) -> None:
        respx.get("https://example.com/start").mock(
            return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        )
        with pytest.raises(UnsafeURLError):
            await safe_fetch("https://example.com/start")

    @respx.mock
    async def test_redirect_to_cloud_metadata_rejected(self) -> None:
        respx.get("https://example.com/start").mock(
            return_value=httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            )
        )
        with pytest.raises(UnsafeURLError):
            await safe_fetch("https://example.com/start")

    @respx.mock
    async def test_redirect_to_private_range_rejected(self) -> None:
        respx.get("https://example.com/start").mock(
            return_value=httpx.Response(302, headers={"location": "http://192.168.1.1/"})
        )
        with pytest.raises(UnsafeURLError):
            await safe_fetch("https://example.com/start")

    @respx.mock
    async def test_second_hop_to_private_rejected(self) -> None:
        """Validation must run on every hop, not only the first."""
        respx.get("https://example.com/a").mock(
            return_value=httpx.Response(302, headers={"location": "https://example.com/b"})
        )
        respx.get("https://example.com/b").mock(
            return_value=httpx.Response(302, headers={"location": "http://10.0.0.1/"})
        )
        with pytest.raises(UnsafeURLError):
            await safe_fetch("https://example.com/a")

    @respx.mock
    async def test_redirect_to_bad_scheme_rejected(self) -> None:
        respx.get("https://example.com/start").mock(
            return_value=httpx.Response(302, headers={"location": "file:///etc/passwd"})
        )
        with pytest.raises(UnsafeURLError):
            await safe_fetch("https://example.com/start")

    @respx.mock
    async def test_redirect_loop_terminates(self) -> None:
        respx.get("https://example.com/loop").mock(
            return_value=httpx.Response(302, headers={"location": "https://example.com/loop"})
        )
        with pytest.raises(FetchError, match=r"[Tt]oo many redirects"):
            await safe_fetch("https://example.com/loop")

    @respx.mock
    async def test_legitimate_redirect_followed(self) -> None:
        respx.get("https://example.com/old").mock(
            return_value=httpx.Response(301, headers={"location": "https://example.com/new"})
        )
        respx.get("https://example.com/new").mock(
            return_value=httpx.Response(
                200,
                html="<html><body>Article</body></html>",
            )
        )
        result = await safe_fetch("https://example.com/old")
        assert result.ok
        assert result.final_url == "https://example.com/new"
        assert result.redirect_chain == ["https://example.com/old"]


@pytest.mark.usefixtures("allow_public_dns", "no_pinning")
class TestSizeLimits:
    @respx.mock
    async def test_oversized_declared_length_rejected(self) -> None:
        respx.get("https://example.com/big").mock(
            return_value=httpx.Response(
                200,
                headers={"content-length": "999999999", "content-type": "text/html"},
                content=b"x",
            )
        )
        with pytest.raises(FetchError, match="larger than the permitted size"):
            await safe_fetch("https://example.com/big", max_bytes=1024)

    @respx.mock
    async def test_body_truncated_at_cap_while_streaming(self) -> None:
        """A body that under-declares its length must still be capped.

        The declared-length check cannot be the only defense: a hostile server
        can send no content-length at all (chunked) or simply lie, so the cap has
        to hold while bytes are arriving.
        """

        async def _endless_body():  # type: ignore[no-untyped-def]
            for _ in range(1000):
                yield b"A" * 1000

        respx.get("https://example.com/lying").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/html"},  # no content-length
                content=_endless_body(),
            )
        )
        result = await safe_fetch("https://example.com/lying", max_bytes=1000)
        assert result.truncated
        assert len(result.content) <= 1000


@pytest.mark.usefixtures("allow_public_dns", "no_pinning")
class TestContentHandling:
    @respx.mock
    async def test_unsupported_content_type_rejected(self) -> None:
        respx.get("https://example.com/binary").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "application/octet-stream"}, content=b"\x00\x01"
            )
        )
        with pytest.raises(FetchError, match="unsupported content type"):
            await safe_fetch("https://example.com/binary")

    @respx.mock
    async def test_http_error_status_reported(self) -> None:
        respx.get("https://example.com/gone").mock(
            return_value=httpx.Response(404, headers={"content-type": "text/html"}, text="nope")
        )
        with pytest.raises(FetchError, match="HTTP 404"):
            await safe_fetch("https://example.com/gone")

    @respx.mock
    async def test_timeout_reported_as_fetch_error(self) -> None:
        respx.get("https://example.com/slow").mock(side_effect=httpx.ConnectTimeout("timed out"))
        with pytest.raises(FetchError, match="timed out"):
            await safe_fetch("https://example.com/slow")

    @respx.mock
    async def test_successful_fetch_returns_text(self) -> None:
        respx.get("https://example.com/article").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><body><h1>Headline</h1></body></html>",
            )
        )
        result = await safe_fetch("https://example.com/article")
        assert result.ok
        assert result.content_type == "text/html"
        assert "Headline" in result.text
        assert not result.truncated


class TestPreFlightValidation:
    """Unsafe URLs must be rejected before any network activity."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://169.254.169.254/",
            "file:///etc/passwd",
            "http://localhost:8080/",
            "http://192.168.1.1/",
        ],
    )
    async def test_unsafe_urls_never_fetched(self, url: str) -> None:
        with pytest.raises(UnsafeURLError):
            await safe_fetch(url)


class TestDNSValidation:
    async def test_private_dns_answer_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A public hostname resolving to a private address must be refused."""
        import socket as _socket

        def _fake_getaddrinfo(host, port, **kwargs):  # type: ignore[no-untyped-def]
            return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

        monkeypatch.setattr(_socket, "getaddrinfo", _fake_getaddrinfo)
        with pytest.raises(UnsafeURLError):
            await safe_fetch("https://evil.example.com/")

    async def test_mixed_dns_answer_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One bad address poisons the whole host.

        Filtering down to the "safe" address would leave a race in which the
        resolver hands the private one to the actual connection.
        """
        import socket as _socket

        def _fake_getaddrinfo(host, port, **kwargs):  # type: ignore[no-untyped-def]
            return [
                (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port)),
                (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),
            ]

        monkeypatch.setattr(_socket, "getaddrinfo", _fake_getaddrinfo)
        with pytest.raises(UnsafeURLError):
            await safe_fetch("https://mixed.example.com/")

    async def test_unresolvable_host_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import socket as _socket

        def _fake_getaddrinfo(host, port, **kwargs):  # type: ignore[no-untyped-def]
            raise _socket.gaierror("name resolution failed")

        monkeypatch.setattr(_socket, "getaddrinfo", _fake_getaddrinfo)
        with pytest.raises(FetchError, match="Could not resolve"):
            await safe_fetch("https://nonexistent.example.com/")
