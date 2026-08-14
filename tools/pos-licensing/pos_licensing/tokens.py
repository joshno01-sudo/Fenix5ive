"""Signed activation tokens.

When the license server accepts an activation or heartbeat it hands the POS
a short-lived token: ``base64url(json payload) . base64url(ed25519 sig)``.
The POS verifies it offline with the embedded public key, so between
heartbeats the app needs no network at all. The expiry on the token *is*
the offline grace period — when the server can't be reached the app keeps
running until the token runs out, and a revoked key simply never gets a
fresh token again.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass

from . import ed25519

TOKEN_VERSION = 1


class TokenError(ValueError):
    """Token is malformed, forged, expired, or for another machine."""


@dataclass(frozen=True)
class TokenPayload:
    key_id: str
    fingerprint: str
    customer: str
    issued_at: int
    expires_at: int

    def expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def issue(payload: TokenPayload, signing_key: bytes) -> str:
    body = json.dumps(
        {
            "v": TOKEN_VERSION,
            "kid": payload.key_id,
            "fp": payload.fingerprint,
            "cus": payload.customer,
            "iat": payload.issued_at,
            "exp": payload.expires_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _b64e(body) + "." + _b64e(ed25519.sign(body, signing_key))


def verify(token: str, public_key: bytes) -> TokenPayload:
    """Check the signature and structure; raises TokenError on any problem.

    Expiry and fingerprint are *not* checked here — the caller compares them
    so it can distinguish "expired" from "forged" and react differently.
    """
    try:
        body_b64, sig_b64 = token.strip().split(".")
        body = _b64d(body_b64)
        sig = _b64d(sig_b64)
    except (ValueError, AttributeError) as exc:
        raise TokenError("malformed token") from exc
    if not ed25519.verify(sig, body, public_key):
        raise TokenError("bad signature")
    try:
        data = json.loads(body)
        if data["v"] != TOKEN_VERSION:
            raise TokenError("unknown token version")
        return TokenPayload(
            key_id=str(data["kid"]),
            fingerprint=str(data["fp"]),
            customer=str(data["cus"]),
            issued_at=int(data["iat"]),
            expires_at=int(data["exp"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TokenError):
            raise
        raise TokenError("malformed token payload") from exc
