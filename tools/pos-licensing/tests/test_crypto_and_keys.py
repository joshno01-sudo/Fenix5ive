import pytest

from pos_licensing import ed25519, keys, tokens


def test_sign_verify_roundtrip():
    sk = ed25519.create_signing_key()
    pk = ed25519.publickey(sk)
    msg = b"the fenix pos license payload"
    sig = ed25519.sign(msg, sk)
    assert len(sig) == 64
    assert ed25519.verify(sig, msg, pk)


def test_verify_rejects_tampering():
    sk = ed25519.create_signing_key()
    pk = ed25519.publickey(sk)
    sig = ed25519.sign(b"paid for one seat", sk)
    assert not ed25519.verify(sig, b"paid for two seats", pk)
    bad_sig = bytes([sig[0] ^ 1]) + sig[1:]
    assert not ed25519.verify(bad_sig, b"paid for one seat", pk)
    other_pk = ed25519.publickey(ed25519.create_signing_key())
    assert not ed25519.verify(sig, b"paid for one seat", other_pk)


def test_key_generation_and_checksum():
    key = keys.generate()
    assert key.startswith("FNX5-")
    assert keys.is_valid_format(key)
    assert keys.canonical(key) == key
    # a single-character typo must fail the checksum
    ch = "7" if key[-1] != "7" else "8"
    assert not keys.is_valid_format(key[:-1] + ch)


def test_key_normalization_is_forgiving():
    key = keys.generate()
    sloppy = key.lower().replace("-", " ")
    assert keys.is_valid_format(sloppy)
    assert keys.canonical(sloppy) == key


def test_key_ids_are_stable():
    key = keys.generate()
    assert keys.key_id(key) == key.split("-")[1]


def test_token_roundtrip_and_forgery():
    sk = ed25519.create_signing_key()
    pk = ed25519.publickey(sk)
    payload = tokens.TokenPayload(key_id="ABCDE", fingerprint="f" * 32,
                                  customer="Test Shop", issued_at=1000,
                                  expires_at=2000)
    token = tokens.issue(payload, sk)
    assert tokens.verify(token, pk) == payload

    with pytest.raises(tokens.TokenError):
        tokens.verify(token, ed25519.publickey(ed25519.create_signing_key()))
    body, sig = token.split(".")
    with pytest.raises(tokens.TokenError):
        tokens.verify(body + "x." + sig, pk)
    with pytest.raises(tokens.TokenError):
        tokens.verify("not-a-token", pk)
