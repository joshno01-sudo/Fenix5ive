"""Pure-Python Ed25519 signing and verification.

Based on the public-domain reference implementation (Bernstein et al.).
No third-party packages, so it runs on a locked-down shop PC — the same
constraint as the rest of the tools in this repo. It is slow (tens of
milliseconds per operation) but license checks happen once at startup and
a few times a day, so that does not matter here.

The private (signing) key lives only with the vendor / license server.
The public (verify) key is embedded in the POS build.
"""

from __future__ import annotations

import hashlib
import os

b = 256
q = 2 ** 255 - 19
l = 2 ** 252 + 27742317777372353535851937790883648493


def _H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def _inv(x: int) -> int:
    return pow(x, q - 2, q)


d = -121665 * _inv(121666) % q
I = pow(2, (q - 1) // 4, q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(d * y * y + 1)
    x = pow(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


_By = 4 * _inv(5) % q
_Bx = _xrecover(_By)
_B = (_Bx, _By)


def _edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - d * x1 * x2 * y1 * y2)
    return (x3 % q, y3 % q)


def _scalarmult(P, e: int):
    Q = (0, 1)
    while e > 0:
        if e & 1:
            Q = _edwards(Q, P)
        P = _edwards(P, P)
        e >>= 1
    return Q


def _encodeint(y: int) -> bytes:
    return y.to_bytes(b // 8, "little")


def _encodepoint(P) -> bytes:
    x, y = P
    n = y | ((x & 1) << (b - 1))
    return n.to_bytes(b // 8, "little")


def _decodeint(s: bytes) -> int:
    return int.from_bytes(s, "little")


def _isoncurve(P) -> bool:
    x, y = P
    return (-x * x + y * y - 1 - d * x * x * y * y) % q == 0


def _decodepoint(s: bytes):
    n = int.from_bytes(s, "little")
    y = n & ((1 << (b - 1)) - 1)
    x = _xrecover(y)
    if x & 1 != (n >> (b - 1)) & 1:
        x = q - x
    P = (x, y)
    if not _isoncurve(P):
        raise ValueError("point is not on the curve")
    return P


def _Hint(m: bytes) -> int:
    return int.from_bytes(_H(m), "little")


def _clamp(h: bytes) -> int:
    a = int.from_bytes(h[: b // 8], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a


def create_signing_key() -> bytes:
    """Return a new random 32-byte signing (private) key."""
    return os.urandom(32)


def publickey(sk: bytes) -> bytes:
    """Derive the 32-byte public verify key from a signing key."""
    a = _clamp(_H(sk))
    return _encodepoint(_scalarmult(_B, a))


def sign(message: bytes, sk: bytes) -> bytes:
    """Sign *message*; returns a 64-byte signature."""
    h = _H(sk)
    a = _clamp(h)
    pk = _encodepoint(_scalarmult(_B, a))
    r = _Hint(h[b // 8 : b // 4] + message)
    R = _scalarmult(_B, r)
    S = (r + _Hint(_encodepoint(R) + pk + message) * a) % l
    return _encodepoint(R) + _encodeint(S)


def verify(signature: bytes, message: bytes, pk: bytes) -> bool:
    """True if *signature* over *message* checks out against public key *pk*."""
    if len(signature) != b // 4 or len(pk) != b // 8:
        return False
    try:
        R = _decodepoint(signature[: b // 8])
        A = _decodepoint(pk)
    except ValueError:
        return False
    S = _decodeint(signature[b // 8 : b // 4])
    if S >= l:
        return False
    h = _Hint(signature[: b // 8] + pk + message)
    return _scalarmult(_B, S) == _edwards(R, _scalarmult(A, h))
