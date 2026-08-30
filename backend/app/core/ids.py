"""Opaque public identifiers.

Serial database ids are never exposed. Public ids are prefixed, URL-safe, and
generated from a CSPRNG so they cannot be enumerated or guessed -- which is what
keeps unlisted verifications effectively private without an auth system.
"""

from __future__ import annotations

import secrets
from typing import Final

# Crockford-style alphabet: no look-alike characters (0/O, 1/I/l), so ids
# survive being read aloud, copied from a screenshot, or typed by hand.
_ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZabcdefghjkmnpqrstvwxyz"
_DEFAULT_LENGTH: Final[int] = 16

SUBMISSION_PREFIX: Final[str] = "sub"
VERIFICATION_PREFIX: Final[str] = "vfy"
MEDIA_PREFIX: Final[str] = "med"


def generate_public_id(prefix: str, length: int = _DEFAULT_LENGTH) -> str:
    """Return an opaque public id such as ``vfy_7gK2mP8dLwQ3nRt5``.

    With a 54-character alphabet and 16 characters this carries roughly 92 bits
    of entropy, which is far beyond guessing range.
    """
    if not prefix:
        raise ValueError("prefix must not be empty")
    if length < 8:
        raise ValueError("public id length must be at least 8 characters")
    body = "".join(secrets.choice(_ALPHABET) for _ in range(length))
    return f"{prefix}_{body}"


def new_submission_id() -> str:
    return generate_public_id(SUBMISSION_PREFIX)


def new_verification_id() -> str:
    return generate_public_id(VERIFICATION_PREFIX)


def new_media_id() -> str:
    return generate_public_id(MEDIA_PREFIX)


def is_valid_public_id(value: str, expected_prefix: str | None = None) -> bool:
    """Validate shape before it ever reaches a database query."""
    if not value or "_" not in value:
        return False
    prefix, _, body = value.partition("_")
    if expected_prefix is not None and prefix != expected_prefix:
        return False
    if not prefix.isalpha() or not 2 <= len(prefix) <= 8:
        return False
    if not 8 <= len(body) <= 32:
        return False
    return all(c in _ALPHABET for c in body)
