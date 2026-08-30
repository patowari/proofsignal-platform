"""Image analysis: metadata, provenance, and text extraction.

What this module reports and, more importantly, what it refuses to report.

**We do not claim to detect AI-generated images.** No reliable general detector
exists. Published tools score roughly 60-80% on curated benchmarks and degrade
badly on the ordinary transformations every shared image goes through --
recompression, resizing, screenshotting, re-upload. A tool that answers
"AI-generated: yes/no" at that accuracy is worse than no tool, because people
act on the answer. Telling someone a real photograph of a real event is
synthetic is a serious harm; so is clearing a fabrication.

What we do instead is report the evidence we actually have, and say what each
signal does and does not establish:

- **C2PA / Content Credentials.** A cryptographically signed provenance
  manifest. When present this is real evidence -- generators including DALL-E
  and Adobe Firefly embed one. Absence proves nothing: the standard is young
  and any re-encode strips it.
- **Generator metadata.** Some tools leave their name in EXIF or PNG text
  chunks. Trivially removable, so presence is informative and absence is not.
- **Camera metadata.** Make, model, lens, exposure. Consistent camera EXIF is
  weak evidence of a photograph; its absence is *not* evidence of generation,
  because every major social platform strips EXIF on upload.
- **Editing software.** A name in the software field means the file passed
  through an editor. Most published photographs have. Not a manipulation
  finding.

Each signal is returned with an explicit confidence and a plain-language note
on its limits. The report shows these as observations, never as a verdict.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

#: Strings left in metadata by known generators. Presence is meaningful;
#: absence means nothing, since a single re-save removes it.
_GENERATOR_MARKERS: tuple[tuple[str, str], ...] = (
    ("stable diffusion", "Stable Diffusion"),
    ("stablediffusion", "Stable Diffusion"),
    ("midjourney", "Midjourney"),
    ("dall-e", "DALL-E"),
    ("dalle", "DALL-E"),
    ("openai", "OpenAI"),
    ("firefly", "Adobe Firefly"),
    ("adobe firefly", "Adobe Firefly"),
    ("imagen", "Google Imagen"),
    ("gemini", "Google Gemini"),
    ("flux", "FLUX"),
    ("leonardo.ai", "Leonardo AI"),
    ("nightcafe", "NightCafe"),
    ("novelai", "NovelAI"),
    ("comfyui", "ComfyUI"),
    ("automatic1111", "AUTOMATIC1111"),
    ("invokeai", "InvokeAI"),
    ("craiyon", "Craiyon"),
    ("bing image creator", "Bing Image Creator"),
    ("grok", "Grok"),
)

#: PNG text chunks where generation tools record parameters.
_GENERATION_PARAM_KEYS = frozenset(
    {"parameters", "prompt", "workflow", "negative_prompt", "sd-metadata", "comment"}
)

#: Editing software. Reported as context, never as a manipulation finding --
#: nearly every published photograph is processed.
_EDITOR_MARKERS = (
    "photoshop",
    "lightroom",
    "gimp",
    "affinity",
    "capture one",
    "snapseed",
    "picsart",
    "canva",
    "figma",
    "pixlr",
)


@dataclass(slots=True)
class ForensicSignal:
    """One observation about a file, with its evidential limits stated."""

    #: Machine key, e.g. "c2pa_manifest_present".
    key: str
    #: What was observed, in plain language.
    finding: str
    #: What this does and does not establish. Always populated -- a signal
    #: without its limits is how a hint becomes a false conclusion.
    caveat: str
    #: strong | moderate | weak
    strength: str = "weak"


@dataclass(slots=True)
class ImageForensics:
    """Everything we can honestly say about an image file."""

    width: int | None = None
    height: int | None = None
    format: str | None = None
    #: Camera/EXIF fields we could read.
    camera: dict[str, Any] = field(default_factory=dict)
    captured_at: datetime | None = None
    #: Software that touched the file, if named.
    software: str | None = None
    #: Named generator found in metadata, if any.
    generator: str | None = None
    #: True when a C2PA/Content Credentials manifest is present.
    has_c2pa: bool = False
    #: Whether EXIF was present at all. Absence is normal after social upload.
    has_exif: bool = False
    signals: list[ForensicSignal] = field(default_factory=list)

    @property
    def ai_generation_assessment(self) -> str:
        """A conservative statement about generation, never a verdict.

        Only positive metadata evidence produces a finding. Nothing else does:
        we do not infer generation from the absence of camera data, from
        resolution, or from anything else that also describes ordinary
        screenshots and re-saved photos.
        """
        if self.generator:
            return "declared_generator"
        if self.has_c2pa:
            return "provenance_present"
        return "undetermined"


def _decode_exif(image: Any) -> dict[str, Any]:
    """Read EXIF into plain values, tolerating malformed tags."""
    try:
        from PIL.ExifTags import GPSTAGS, TAGS
    except Exception:
        return {}

    try:
        raw = image.getexif()
    except Exception:
        return {}
    if not raw:
        return {}

    data: dict[str, Any] = {}
    for tag_id, value in raw.items():
        name = TAGS.get(tag_id, str(tag_id))
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", errors="replace").strip("\x00")
            except Exception:
                value = f"<{len(value)} bytes>"
        data[name] = value

    # GPS lives in its own IFD.
    try:
        gps_ifd = raw.get_ifd(0x8825)
        if gps_ifd:
            data["GPSInfo"] = {GPSTAGS.get(k, str(k)): v for k, v in gps_ifd.items()}
    except Exception as exc:
        # GPS is optional and its IFD is frequently malformed. Losing it must
        # not cost us the rest of the metadata.
        logger.debug("image_analysis.gps_unreadable", error_type=type(exc).__name__)

    return data


def _parse_exif_datetime(value: Any) -> datetime | None:
    """EXIF dates use 'YYYY:MM:DD HH:MM:SS'."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _find_generator(haystack: str) -> str | None:
    lowered = haystack.lower()
    for marker, label in _GENERATOR_MARKERS:
        if marker in lowered:
            return label
    return None


def _detect_c2pa(data: bytes) -> bool:
    """Look for a C2PA / Content Credentials manifest.

    Byte-level detection of the JUMBF box and its namespace. This finds that a
    manifest exists; it does not validate the signature, so we describe it as
    "present" rather than "verified".
    """
    window = data[:200_000]
    return b"c2pa" in window.lower() or b"jumb" in window[:8000].lower()


def analyze_image(data: bytes) -> ImageForensics:
    """Extract every honest signal from an image file.

    Never raises: a file we cannot parse yields an empty result with a stated
    reason, because failing to read a file says nothing about its authenticity.
    """
    result = ImageForensics()

    try:
        from PIL import Image
    except Exception:
        return result

    try:
        with Image.open(io.BytesIO(data)) as image:
            result.width, result.height = image.size
            result.format = image.format

            exif = _decode_exif(image)
            result.has_exif = bool(exif)

            if exif:
                for key in (
                    "Make",
                    "Model",
                    "LensModel",
                    "FNumber",
                    "ISOSpeedRatings",
                    "ExposureTime",
                ):
                    if key in exif:
                        result.camera[key] = str(exif[key])[:120]
                result.captured_at = _parse_exif_datetime(
                    exif.get("DateTimeOriginal") or exif.get("DateTime")
                )
                if "Software" in exif:
                    result.software = str(exif["Software"])[:120]

            # PNG text chunks: where most generation tools record prompts.
            png_text = ""
            info = getattr(image, "info", {}) or {}
            for key, value in info.items():
                if isinstance(value, str) and (
                    key.lower() in _GENERATION_PARAM_KEYS or len(value) < 4000
                ):
                    png_text += f" {key}: {value}"

            searchable = " ".join(
                [
                    png_text,
                    result.software or "",
                    str(exif.get("ImageDescription", "")),
                    str(exif.get("Artist", "")),
                    str(exif.get("Copyright", "")),
                ]
            )
            result.generator = _find_generator(searchable)

    except Exception as exc:
        logger.info("image_analysis.unreadable", error_type=type(exc).__name__)
        return result

    result.has_c2pa = _detect_c2pa(data)
    result.signals = _build_signals(result)
    return result


def _build_signals(f: ImageForensics) -> list[ForensicSignal]:
    """Turn raw findings into observations with their limits attached.

    Every signal carries a caveat. That is the point: a finding without its
    limits is how "no camera metadata" becomes "this is AI-generated".
    """
    signals: list[ForensicSignal] = []

    if f.generator:
        signals.append(
            ForensicSignal(
                key="generator_metadata",
                finding=f"The file's metadata names {f.generator}.",
                caveat=(
                    "This is strong evidence the image was produced or processed by that "
                    "tool. Metadata can be edited, so it is not proof."
                ),
                strength="strong",
            )
        )

    if f.has_c2pa:
        signals.append(
            ForensicSignal(
                key="c2pa_present",
                finding="The file carries a Content Credentials (C2PA) provenance manifest.",
                caveat=(
                    "We detected the manifest but did not validate its signature. "
                    "Both cameras and AI generators attach these."
                ),
                strength="moderate",
            )
        )

    if f.camera:
        make = f.camera.get("Make", "").strip()
        model = f.camera.get("Model", "").strip()
        device = f"{make} {model}".strip() or "a camera"
        signals.append(
            ForensicSignal(
                key="camera_metadata",
                finding=f"The file carries camera metadata ({device}).",
                caveat=(
                    "Consistent with a photograph, but camera metadata can be copied "
                    "onto any file, so it is suggestive rather than conclusive."
                ),
                strength="moderate",
            )
        )
    elif not f.has_exif:
        # Stated carefully: this is the single most misread signal in image
        # forensics, and the caveat is the whole point of reporting it.
        signals.append(
            ForensicSignal(
                key="no_metadata",
                finding="The file carries no EXIF metadata.",
                caveat=(
                    "This is normal and expected: Facebook, WhatsApp, X and most other "
                    "platforms strip metadata from every upload, and screenshots never "
                    "have it. It is NOT an indication that the image is AI-generated."
                ),
                strength="weak",
            )
        )

    if f.software:
        lowered = f.software.lower()
        if any(editor in lowered for editor in _EDITOR_MARKERS):
            signals.append(
                ForensicSignal(
                    key="editing_software",
                    finding=f"The file was saved by {f.software}.",
                    caveat=(
                        "Editing software was used at some point. Nearly every published "
                        "photograph is processed, so this is not a sign of manipulation."
                    ),
                    strength="weak",
                )
            )

    if f.captured_at:
        signals.append(
            ForensicSignal(
                key="capture_date",
                finding=f"Metadata records a capture date of {f.captured_at:%d %b %Y}.",
                caveat=(
                    "Useful for checking whether the file predates the event it is said "
                    "to show. Capture dates can be altered."
                ),
                strength="moderate",
            )
        )

    return signals


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


def ocr_available() -> tuple[bool, str]:
    """Whether an OCR engine is usable. Returns (available, reason)."""
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract is not installed"

    try:
        from app.core.config import get_settings

        pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_path
        pytesseract.get_tesseract_version()
        return True, ""
    except Exception as exc:
        return False, f"the Tesseract binary was not found ({type(exc).__name__})"


def extract_text(data: bytes, *, languages: str = "eng+ben") -> tuple[str | None, str]:
    """Read text from an image. Returns (text, unavailable_reason).

    A missing engine returns (None, reason) so the report can say "we could not
    read the text" rather than "no text found" -- our gap must never be
    presented as a finding about the user's file.
    """
    available, reason = ocr_available()
    if not available:
        return None, reason

    try:
        import pytesseract
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            text = pytesseract.image_to_string(image, lang=languages)
    except Exception as exc:
        return None, f"text extraction failed ({type(exc).__name__})"

    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    return (cleaned or ""), ""
