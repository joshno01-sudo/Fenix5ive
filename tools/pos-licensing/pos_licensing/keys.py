"""License key format.

Keys look like ``FNX5-C3KP7-M2Q9D-X4RTV-8W6HN``: a fixed prefix, then twenty
characters of Crockford base32 — sixteen random, four checksum. The checksum
lets the POS reject a mistyped key instantly, before it ever hits the
network; it carries no rights by itself. All entitlement lives server-side:
the key is only a lookup handle the license server resolves to a customer
record, seat count and revocation state.
"""

from __future__ import annotations

import hashlib
import secrets

PREFIX = "FNX5"

# Crockford base32: no I, L, O, U — unambiguous to read over the phone.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_RANDOM_CHARS = 16
_CHECK_CHARS = 4


def _checksum(body: str) -> str:
    digest = hashlib.sha256((PREFIX + body).encode("ascii")).digest()
    n = int.from_bytes(digest[:4], "big")
    out = []
    for _ in range(_CHECK_CHARS):
        out.append(_ALPHABET[n & 31])
        n >>= 5
    return "".join(out)


def _group(chars: str) -> str:
    groups = [chars[i : i + 5] for i in range(0, len(chars), 5)]
    return "-".join([PREFIX] + groups)


def generate() -> str:
    """Generate a fresh license key."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_RANDOM_CHARS))
    return _group(body + _checksum(body))


def normalize(key: str) -> str:
    """Uppercase, strip separators/whitespace, map easily-confused letters."""
    cleaned = key.strip().upper().replace("-", "").replace(" ", "")
    if cleaned.startswith(PREFIX):
        cleaned = cleaned[len(PREFIX) :]
    # Crockford aliases for characters the alphabet excludes.
    cleaned = cleaned.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))
    return cleaned


def is_valid_format(key: str) -> bool:
    """True if the key is well-formed and its checksum matches."""
    cleaned = normalize(key)
    if len(cleaned) != _RANDOM_CHARS + _CHECK_CHARS:
        return False
    if any(c not in _ALPHABET for c in cleaned):
        return False
    body, check = cleaned[:_RANDOM_CHARS], cleaned[_RANDOM_CHARS:]
    return _checksum(body) == check


def canonical(key: str) -> str:
    """Return the display form (FNX5-XXXXX-...) of a valid key.

    Raises ValueError if the key fails the checksum.
    """
    if not is_valid_format(key):
        raise ValueError("not a valid license key")
    return _group(normalize(key))


def key_id(key: str) -> str:
    """Short identifier used in the database and admin CLI: first group."""
    return canonical(key).split("-")[1]
