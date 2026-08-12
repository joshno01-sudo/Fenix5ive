"""Minimal, dependency-free SNMP v1/v2c client.

Only the pieces a printer monitor needs: GET, GETNEXT, GETBULK and a table
walk, with BER encode/decode written from scratch so the app has no external
dependencies (important for locked-down shop-floor PCs).

Reference: RFC 1157 (SNMPv1), RFC 3416 (SNMPv2c PDUs), X.690 (BER).
"""

from __future__ import annotations

import random
import socket
from dataclasses import dataclass
from typing import Iterator, Sequence

# ---------------------------------------------------------------------------
# BER tags
# ---------------------------------------------------------------------------

TAG_INTEGER = 0x02
TAG_OCTET_STRING = 0x04
TAG_NULL = 0x05
TAG_OID = 0x06
TAG_SEQUENCE = 0x30

TAG_IP_ADDRESS = 0x40
TAG_COUNTER32 = 0x41
TAG_GAUGE32 = 0x42
TAG_TIMETICKS = 0x43
TAG_OPAQUE = 0x44
TAG_COUNTER64 = 0x46

TAG_NO_SUCH_OBJECT = 0x80
TAG_NO_SUCH_INSTANCE = 0x81
TAG_END_OF_MIB_VIEW = 0x82

PDU_GET = 0xA0
PDU_GET_NEXT = 0xA1
PDU_RESPONSE = 0xA2
PDU_SET = 0xA3
PDU_GET_BULK = 0xA5

VERSION_1 = 0
VERSION_2C = 1

# SNMPv1 error-status values we care about
ERR_NO_ERROR = 0
ERR_TOO_BIG = 1
ERR_NO_SUCH_NAME = 2
ERR_BAD_VALUE = 3
ERR_READ_ONLY = 4
ERR_GEN_ERR = 5

_ERROR_NAMES = {
    ERR_NO_ERROR: "noError",
    ERR_TOO_BIG: "tooBig",
    ERR_NO_SUCH_NAME: "noSuchName",
    ERR_BAD_VALUE: "badValue",
    ERR_READ_ONLY: "readOnly",
    ERR_GEN_ERR: "genErr",
}


class SnmpError(Exception):
    """Base class for SNMP failures."""


class SnmpTimeout(SnmpError):
    """No response from the agent within the configured timeout/retries."""


class SnmpResponseError(SnmpError):
    """The agent answered with a non-zero error-status."""

    def __init__(self, status: int, index: int):
        self.status = status
        self.index = index
        name = _ERROR_NAMES.get(status, f"status {status}")
        super().__init__(f"SNMP agent returned {name} (error-index {index})")


class _Sentinel:
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<{self.name}>"


NO_SUCH_OBJECT = _Sentinel("noSuchObject")
NO_SUCH_INSTANCE = _Sentinel("noSuchInstance")
END_OF_MIB_VIEW = _Sentinel("endOfMibView")

_MISSING = (NO_SUCH_OBJECT, NO_SUCH_INSTANCE, END_OF_MIB_VIEW)


def is_missing(value: object) -> bool:
    """True when a varbind value means "this object does not exist here"."""
    return value in _MISSING or value is None


# ---------------------------------------------------------------------------
# OID helpers
# ---------------------------------------------------------------------------

OID = tuple  # alias for readability: an OID is a tuple[int, ...]


def parse_oid(text: str | Sequence[int]) -> tuple[int, ...]:
    """Accept ``"1.3.6.1.2.1"``, ``".1.3.6.1"`` or an int sequence."""
    if isinstance(text, str):
        cleaned = text.strip().lstrip(".")
        if not cleaned:
            raise ValueError("empty OID")
        return tuple(int(part) for part in cleaned.split("."))
    return tuple(int(part) for part in text)


def oid_str(oid: Sequence[int]) -> str:
    return ".".join(str(part) for part in oid)


def is_prefix(prefix: Sequence[int], oid: Sequence[int]) -> bool:
    """True when ``oid`` sits at or below ``prefix``."""
    return len(oid) >= len(prefix) and tuple(oid[: len(prefix)]) == tuple(prefix)


# ---------------------------------------------------------------------------
# BER encoding
# ---------------------------------------------------------------------------


def _enc_len(length: int) -> bytes:
    if length < 0x80:
        return bytes((length,))
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(raw),)) + raw


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes((tag,)) + _enc_len(len(body)) + body


def _int_body(value: int) -> bytes:
    size = 1
    while True:
        try:
            return value.to_bytes(size, "big", signed=True)
        except OverflowError:
            size += 1


def _enc_int(value: int) -> bytes:
    return _tlv(TAG_INTEGER, _int_body(value))


def _enc_octets(value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return _tlv(TAG_OCTET_STRING, value)


def _enc_base128(value: int) -> bytes:
    if value < 0:
        raise ValueError("OID arcs cannot be negative")
    if value == 0:
        return b"\x00"
    chunks = []
    while value:
        chunks.append(value & 0x7F)
        value >>= 7
    chunks.reverse()
    return bytes([c | 0x80 for c in chunks[:-1]] + [chunks[-1]])


def _enc_oid(oid: Sequence[int]) -> bytes:
    arcs = list(oid)
    if len(arcs) < 2:
        raise ValueError("OID needs at least two arcs")
    if arcs[0] > 2 or arcs[0] < 0:
        raise ValueError("first OID arc must be 0, 1 or 2")
    body = _enc_base128(arcs[0] * 40 + arcs[1])
    for arc in arcs[2:]:
        body += _enc_base128(arc)
    return _tlv(TAG_OID, body)


# ---------------------------------------------------------------------------
# BER decoding
# ---------------------------------------------------------------------------


def _dec_tlv(data: bytes, pos: int) -> tuple[int, bytes, int]:
    """Return ``(tag, body, next_pos)``."""
    if pos + 2 > len(data):
        raise SnmpError("truncated SNMP message (header)")
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0:
            raise SnmpError("indefinite BER lengths are not supported")
        if pos + count > len(data):
            raise SnmpError("truncated SNMP message (length)")
        length = int.from_bytes(data[pos : pos + count], "big")
        pos += count
    end = pos + length
    if end > len(data):
        raise SnmpError("truncated SNMP message (body)")
    return tag, data[pos:end], end


def _dec_int(body: bytes) -> int:
    if not body:
        return 0
    return int.from_bytes(body, "big", signed=True)


def _dec_uint(body: bytes) -> int:
    return int.from_bytes(body, "big", signed=False) if body else 0


def _dec_oid(body: bytes) -> tuple[int, ...]:
    if not body:
        return ()
    first = body[0]
    if first < 40:
        arcs = [0, first]
    elif first < 80:
        arcs = [1, first - 40]
    else:
        arcs = [2, first - 80]
    value = 0
    started = False
    for byte in body[1:]:
        value = (value << 7) | (byte & 0x7F)
        started = True
        if not byte & 0x80:
            arcs.append(value)
            value = 0
            started = False
    if started:
        raise SnmpError("malformed OID encoding")
    return tuple(arcs)


def _dec_value(tag: int, body: bytes):
    if tag == TAG_INTEGER:
        return _dec_int(body)
    if tag in (TAG_COUNTER32, TAG_GAUGE32, TAG_TIMETICKS, TAG_COUNTER64):
        return _dec_uint(body)
    if tag == TAG_OCTET_STRING:
        return _decode_text(body)
    if tag == TAG_OID:
        return _dec_oid(body)
    if tag == TAG_NULL:
        return None
    if tag == TAG_IP_ADDRESS:
        return ".".join(str(b) for b in body) if len(body) == 4 else body.hex()
    if tag == TAG_NO_SUCH_OBJECT:
        return NO_SUCH_OBJECT
    if tag == TAG_NO_SUCH_INSTANCE:
        return NO_SUCH_INSTANCE
    if tag == TAG_END_OF_MIB_VIEW:
        return END_OF_MIB_VIEW
    if tag == TAG_OPAQUE:
        return body
    return body


def _decode_text(body: bytes) -> str:
    """Printer MIB strings are usually ASCII/UTF-8; fall back to latin-1.

    Some HP firmware pads fields with NULs, so those get trimmed.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            text = body.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 never fails
        text = body.hex()
    return text.replace("\x00", "").strip()


# ---------------------------------------------------------------------------
# Varbinds and messages
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VarBind:
    oid: tuple[int, ...]
    value: object
    # Undecoded octets for OCTET STRING / Opaque values. Needed for bit-string
    # objects such as hrPrinterDetectedErrorState, where the text decoding
    # (which trims NULs and whitespace) would corrupt the flags.
    raw: bytes | None = None

    @property
    def oid_text(self) -> str:
        return oid_str(self.oid)


def _enc_varbind(oid: Sequence[int]) -> bytes:
    return _tlv(TAG_SEQUENCE, _enc_oid(oid) + _tlv(TAG_NULL, b""))


def _build_message(
    version: int,
    community: str,
    pdu_type: int,
    request_id: int,
    oids: Sequence[Sequence[int]],
    error_status: int = 0,
    error_index: int = 0,
) -> bytes:
    varbinds = b"".join(_enc_varbind(oid) for oid in oids)
    pdu_body = (
        _enc_int(request_id)
        + _enc_int(error_status)
        + _enc_int(error_index)
        + _tlv(TAG_SEQUENCE, varbinds)
    )
    pdu = _tlv(pdu_type, pdu_body)
    return _tlv(TAG_SEQUENCE, _enc_int(version) + _enc_octets(community) + pdu)


def _parse_message(data: bytes) -> tuple[int, str, int, int, int, int, list[VarBind]]:
    tag, body, _ = _dec_tlv(data, 0)
    if tag != TAG_SEQUENCE:
        raise SnmpError("SNMP message is not a SEQUENCE")

    pos = 0
    tag, vbody, pos = _dec_tlv(body, pos)
    version = _dec_int(vbody)
    tag, cbody, pos = _dec_tlv(body, pos)
    community = _decode_text(cbody)
    pdu_type, pdu_body, pos = _dec_tlv(body, pos)

    ppos = 0
    _, rid_body, ppos = _dec_tlv(pdu_body, ppos)
    request_id = _dec_int(rid_body)
    _, err_body, ppos = _dec_tlv(pdu_body, ppos)
    error_status = _dec_int(err_body)
    _, idx_body, ppos = _dec_tlv(pdu_body, ppos)
    error_index = _dec_int(idx_body)
    _, vb_body, ppos = _dec_tlv(pdu_body, ppos)

    varbinds: list[VarBind] = []
    vpos = 0
    while vpos < len(vb_body):
        _, one, vpos = _dec_tlv(vb_body, vpos)
        opos = 0
        otag, obody, opos = _dec_tlv(one, opos)
        if otag != TAG_OID:
            raise SnmpError("varbind name is not an OID")
        vtag, vbytes, opos = _dec_tlv(one, opos)
        raw = vbytes if vtag in (TAG_OCTET_STRING, TAG_OPAQUE) else None
        varbinds.append(VarBind(_dec_oid(obody), _dec_value(vtag, vbytes), raw))

    return version, community, pdu_type, request_id, error_status, error_index, varbinds


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class SnmpClient:
    """Synchronous SNMP v1/v2c client over UDP.

    One client per printer. Not thread-safe; the poller uses it from a single
    worker thread at a time.
    """

    def __init__(
        self,
        host: str,
        community: str = "public",
        port: int = 161,
        version: str | int = "2c",
        timeout: float = 3.0,
        retries: int = 2,
        max_repetitions: int = 25,
    ):
        self.host = host
        self.port = int(port)
        self.community = community
        self.version = self._normalize_version(version)
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.max_repetitions = max(1, int(max_repetitions))
        self._request_id = random.randint(1, 0x7FFFFF)

    @staticmethod
    def _normalize_version(version: str | int) -> int:
        """Accept ``"2c"``, ``"v1"``, ``1``, ``2`` — always the human version.

        Deliberately *not* the on-the-wire number: ``1`` means SNMPv1, never
        v2c, so a config file saying ``1`` can't silently select the other one.
        """
        text = str(version).strip().lower().lstrip("v")
        if text in ("1",):
            return VERSION_1
        if text in ("2", "2c"):
            return VERSION_2C
        raise ValueError(f"unsupported SNMP version: {version!r} (use '1' or '2c')")

    @property
    def version_label(self) -> str:
        return "1" if self.version == VERSION_1 else "2c"

    def _next_request_id(self) -> int:
        self._request_id = (self._request_id + 1) & 0x7FFFFFFF or 1
        return self._request_id

    # -- transport ---------------------------------------------------------

    def _exchange(self, pdu_type: int, oids: Sequence[Sequence[int]], **pdu_kw) -> list[VarBind]:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            request_id = self._next_request_id()
            packet = _build_message(
                self.version, self.community, pdu_type, request_id, oids, **pdu_kw
            )
            try:
                reply = self._send_once(packet, request_id)
            except SnmpTimeout as exc:
                last_error = exc
                continue
            return reply
        raise last_error or SnmpTimeout("no response")

    def _send_once(self, packet: bytes, request_id: int) -> list[VarBind]:
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self.timeout)
            sock.sendto(packet, (self.host, self.port))
            # Ignore stale replies from earlier (timed-out) requests.
            while True:
                try:
                    data, _addr = sock.recvfrom(65535)
                except socket.timeout as exc:
                    raise SnmpTimeout(
                        f"{self.host}:{self.port} did not respond within {self.timeout}s"
                    ) from exc
                except OSError as exc:
                    raise SnmpError(f"network error talking to {self.host}: {exc}") from exc
                (
                    _version,
                    _community,
                    pdu_type,
                    resp_id,
                    error_status,
                    error_index,
                    varbinds,
                ) = _parse_message(data)
                if resp_id != request_id:
                    continue
                if pdu_type != PDU_RESPONSE:
                    raise SnmpError(f"unexpected PDU type 0x{pdu_type:02X} in response")
                if error_status != ERR_NO_ERROR:
                    raise SnmpResponseError(error_status, error_index)
                return varbinds
        finally:
            sock.close()

    # -- operations --------------------------------------------------------

    def get(self, *oids: str | Sequence[int]) -> list[VarBind]:
        parsed = [parse_oid(o) for o in oids]
        if not parsed:
            return []
        return self._exchange(PDU_GET, parsed)

    def get_one(self, oid: str | Sequence[int], default=None):
        """GET a single value, returning ``default`` when it is absent."""
        try:
            varbinds = self.get(oid)
        except SnmpResponseError as exc:
            if exc.status == ERR_NO_SUCH_NAME:
                return default
            raise
        if not varbinds:
            return default
        value = varbinds[0].value
        return default if is_missing(value) else value

    def get_raw(self, oid: str | Sequence[int]) -> bytes | None:
        """GET the undecoded octets — for bit-string objects like error states."""
        try:
            varbinds = self.get(oid)
        except SnmpResponseError as exc:
            if exc.status == ERR_NO_SUCH_NAME:
                return None
            raise
        if not varbinds or is_missing(varbinds[0].value):
            return None
        return varbinds[0].raw

    def get_next(self, oid: str | Sequence[int]) -> VarBind | None:
        varbinds = self._exchange(PDU_GET_NEXT, [parse_oid(oid)])
        return varbinds[0] if varbinds else None

    def get_bulk(self, oid: str | Sequence[int], max_repetitions: int | None = None) -> list[VarBind]:
        if self.version == VERSION_1:
            nxt = self.get_next(oid)
            return [nxt] if nxt else []
        reps = max_repetitions or self.max_repetitions
        # In GETBULK the error-status/error-index slots carry non-repeaters and
        # max-repetitions instead.
        return self._exchange(
            PDU_GET_BULK, [parse_oid(oid)], error_status=0, error_index=reps
        )

    def walk(self, base: str | Sequence[int], limit: int = 5000) -> Iterator[VarBind]:
        """Walk the subtree under ``base``, yielding varbinds in OID order."""
        root = parse_oid(base)
        current = root
        seen = 0
        while True:
            try:
                batch = self.get_bulk(current)
            except SnmpResponseError as exc:
                if exc.status in (ERR_NO_SUCH_NAME, ERR_TOO_BIG):
                    return
                raise
            if not batch:
                return
            for vb in batch:
                if not is_prefix(root, vb.oid):
                    return
                if vb.value is END_OF_MIB_VIEW:
                    return
                if vb.oid <= current and vb.oid != root:
                    # Agent stopped advancing — bail rather than loop forever.
                    return
                if is_missing(vb.value):
                    continue
                yield vb
                seen += 1
                if seen >= limit:
                    return
            current = batch[-1].oid

    def walk_column(self, base: str | Sequence[int], limit: int = 5000) -> dict[tuple[int, ...], object]:
        """Walk a table column, keyed by the index arcs below ``base``."""
        root = parse_oid(base)
        out: dict[tuple[int, ...], object] = {}
        for vb in self.walk(root, limit=limit):
            out[tuple(vb.oid[len(root) :])] = vb.value
        return out

    def probe(self) -> bool:
        """Cheap reachability check (sysUpTime)."""
        try:
            self.get_one("1.3.6.1.2.1.1.3.0")
        except SnmpError:
            return False
        return True


def sniff_version(
    host: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 2.0,
) -> str | None:
    """Return the first SNMP version that answers, or ``None``.

    Handy for the HP LaserJet 4100's JetDirect card, which on older firmware
    only speaks SNMPv1.
    """
    for version in ("2c", "1"):
        client = SnmpClient(
            host, community=community, port=port, version=version, timeout=timeout, retries=0
        )
        if client.probe():
            return version
    return None


__all__ = [
    "SnmpClient",
    "SnmpError",
    "SnmpTimeout",
    "SnmpResponseError",
    "VarBind",
    "NO_SUCH_OBJECT",
    "NO_SUCH_INSTANCE",
    "END_OF_MIB_VIEW",
    "is_missing",
    "parse_oid",
    "oid_str",
    "is_prefix",
    "sniff_version",
]
