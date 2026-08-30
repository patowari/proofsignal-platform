"""Upload validation tests.

Uploads are hostile input. These tests assert that we trust the file's bytes
rather than the client's claims about them.
"""

from __future__ import annotations

import io

import pytest

from app.core.enums import MediaKind
from app.core.errors import (
    MediaProcessingError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.security.upload_validation import (
    detect_content_type,
    validate_image_upload,
    validate_video_upload,
)

# Minimal real files. Built rather than committed as binaries so the tests stay
# readable and diffable.
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c6360000002000100ffff0300000600"
    "05fd8b8d3a0000000049454e44ae426082"
)
GIF_1X1 = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


def _make_jpeg(width: int = 8, height: int = 8) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


class TestSignatureDetection:
    def test_detects_real_formats(self) -> None:
        assert detect_content_type(PNG_1X1) == "image/png"
        assert detect_content_type(GIF_1X1) == "image/gif"
        assert detect_content_type(_make_jpeg()) == "image/jpeg"

    def test_detects_mp4_brand_at_offset_four(self) -> None:
        """ISO-BMFF carries its brand after the box size, not at byte 0."""
        mp4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
        assert detect_content_type(mp4) == "video/mp4"

    def test_detects_webm(self) -> None:
        webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 20
        assert detect_content_type(webm) == "video/webm"

    def test_riff_requires_webp_tag(self) -> None:
        """RIFF alone is ambiguous: WAV and AVI share it."""
        wav = b"RIFF\x24\x00\x00\x00WAVEfmt "
        assert detect_content_type(wav) != "image/webp"
        webp = b"RIFF\x24\x00\x00\x00WEBPVP8 "
        assert detect_content_type(webp) == "image/webp"

    def test_unknown_content_returns_none(self) -> None:
        assert detect_content_type(b"just some plain text here") is None
        assert detect_content_type(b"") is None


class TestDeclaredTypeIsNotTrusted:
    def test_mismatched_declared_type_rejected(self) -> None:
        """A PNG declared as JPEG means someone is lying or the file is a polyglot."""
        with pytest.raises(UnsupportedMediaTypeError, match="does not match"):
            validate_image_upload(PNG_1X1, declared_type="image/jpeg")

    def test_executable_disguised_as_image_rejected(self) -> None:
        fake = b"MZ\x90\x00" + b"\x00" * 100  # PE header
        with pytest.raises(UnsupportedMediaTypeError):
            validate_image_upload(fake, declared_type="image/png")

    def test_script_disguised_as_image_rejected(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError):
            validate_image_upload(b"<?php system($_GET[0]); ?>", declared_type="image/png")

    def test_octet_stream_declaration_allowed(self) -> None:
        """Some clients send a generic type; the signature still decides."""
        result = validate_image_upload(PNG_1X1, declared_type="application/octet-stream")
        assert result.content_type == "image/png"

    def test_declared_type_with_charset_parameter_accepted(self) -> None:
        result = validate_image_upload(PNG_1X1, declared_type="image/png; charset=binary")
        assert result.content_type == "image/png"


class TestPolyglots:
    @pytest.mark.parametrize(
        "payload",
        [
            b"GIF89a<html><script>alert(1)</script>",
            b"GIF89a<svg onload=alert(1)>",
            b"GIF89a\x00\x00<?php echo 1; ?>",
        ],
    )
    def test_polyglot_files_rejected(self, payload: str) -> None:
        """Valid as an image to us, executable to a sniffing browser."""
        with pytest.raises(UnsupportedMediaTypeError, match="markup or script"):
            validate_image_upload(payload)

    def test_legitimate_image_not_flagged(self) -> None:
        result = validate_image_upload(_make_jpeg())
        assert result.content_type == "image/jpeg"


class TestSizeLimits:
    def test_oversized_image_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MAX_IMAGE_BYTES", "1000")
        try:
            with pytest.raises(PayloadTooLargeError):
                validate_image_upload(PNG_1X1 + b"\x00" * 2000)
        finally:
            get_settings.cache_clear()

    def test_empty_upload_rejected(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError, match="empty"):
            validate_image_upload(b"")

    def test_dimension_cap_enforced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards against a small file that decodes to an enormous bitmap."""
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MAX_IMAGE_DIMENSION", "16")
        try:
            with pytest.raises(PayloadTooLargeError, match="dimensions"):
                validate_image_upload(_make_jpeg(64, 64))
        finally:
            get_settings.cache_clear()


class TestDecompressionBombs:
    def test_pixel_cap_enforced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A bomb is rejected from the header, before pixels are decoded."""
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MAX_IMAGE_PIXELS", "100")
        try:
            with pytest.raises(PayloadTooLargeError):
                validate_image_upload(_make_jpeg(64, 64))
        finally:
            get_settings.cache_clear()


class TestCorruptFiles:
    def test_truncated_image_reported_clearly(self) -> None:
        truncated = PNG_1X1[:20]
        with pytest.raises((MediaProcessingError, UnsupportedMediaTypeError)):
            validate_image_upload(truncated)

    def test_valid_signature_garbage_body(self) -> None:
        corrupt = b"\x89PNG\r\n\x1a\n" + b"\xff" * 200
        with pytest.raises(MediaProcessingError):
            validate_image_upload(corrupt)


class TestScreenshotKind:
    def test_screenshot_flag_sets_kind(self) -> None:
        """Screenshots are analyzed differently: they prove an image exists,
        not that the depicted post is genuine."""
        assert validate_image_upload(PNG_1X1, is_screenshot=True).kind is MediaKind.SCREENSHOT
        assert validate_image_upload(PNG_1X1, is_screenshot=False).kind is MediaKind.IMAGE


class TestVideoValidation:
    def test_valid_mp4_signature_accepted(self) -> None:
        mp4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00" + b"\x00" * 200
        result = validate_video_upload(mp4)
        assert result.content_type == "video/mp4"
        assert result.kind is MediaKind.VIDEO

    def test_image_rejected_as_video(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError):
            validate_video_upload(PNG_1X1)

    def test_oversized_video_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MAX_VIDEO_BYTES", "500")
        try:
            mp4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 2000
            with pytest.raises(PayloadTooLargeError):
                validate_video_upload(mp4)
        finally:
            get_settings.cache_clear()

    def test_empty_video_rejected(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError, match="empty"):
            validate_video_upload(b"")


class TestStorageKeyGeneration:
    def test_user_filename_never_becomes_a_path(self) -> None:
        """The defense against path traversal is not sanitizing the filename --
        it is never using it."""
        from app.services.storage import generate_storage_key

        for _ in range(50):
            key = generate_storage_key("image/png")
            assert ".." not in key
            assert not key.startswith("/")
            assert "\x00" not in key
            assert key.endswith(".png")

    def test_keys_are_unique(self) -> None:
        from app.services.storage import generate_storage_key

        keys = {generate_storage_key("image/png") for _ in range(200)}
        assert len(keys) == 200

    def test_unknown_type_gets_inert_extension(self) -> None:
        from app.services.storage import generate_storage_key

        assert generate_storage_key("application/x-evil").endswith(".bin")
