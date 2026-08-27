"""A small in-process SNMP agent, so the poller can be tested for real.

Serves a canned MIB over UDP on localhost, speaking v1 (GET/GETNEXT) and v2c
(plus GETBULK). Values are typed from the Python objects in the MIB dict.
"""

from __future__ import annotations

import socket
import threading
from typing import Optional

from printer_monitor.snmp import (
    ERR_NO_SUCH_NAME,
    PDU_GET,
    PDU_GET_BULK,
    PDU_GET_NEXT,
    PDU_RESPONSE,
    TAG_END_OF_MIB_VIEW,
    TAG_INTEGER,
    TAG_NULL,
    TAG_OCTET_STRING,
    TAG_SEQUENCE,
    _dec_tlv,
    _enc_int,
    _enc_octets,
    _enc_oid,
    _parse_message,
    _tlv,
    parse_oid,
)


class FakeAgent:
    """Threaded UDP SNMP agent over a canned ``{oid_string: value}`` MIB."""

    def __init__(
        self,
        mib: dict[str, object],
        community: str = "public",
        versions: tuple[str, ...] = ("1", "2c"),
        drop_first: int = 0,
    ):
        self.mib = {parse_oid(oid): value for oid, value in mib.items()}
        self.order = sorted(self.mib)
        self.community = community
        self.versions = {0 if v == "1" else 1 for v in versions}
        self.drop_first = drop_first  # simulate packet loss, to exercise retries

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.host, self.port = self.sock.getsockname()
        self.request_count = 0

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "FakeAgent":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self) -> "FakeAgent":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)

    # -- serving -----------------------------------------------------------

    def _serve(self) -> None:
        self.sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            self.request_count += 1
            if self.request_count <= self.drop_first:
                continue
            try:
                reply = self._handle(data)
            except Exception:  # noqa: BLE001 - a broken request just gets no reply
                continue
            if reply is not None:
                try:
                    self.sock.sendto(reply, addr)
                except OSError:
                    return

    def _handle(self, data: bytes) -> Optional[bytes]:
        version, community, pdu_type, request_id, field2, field3, varbinds = _parse_message(data)
        if community != self.community or version not in self.versions:
            return None  # a real agent silently drops these too

        oids = [vb.oid for vb in varbinds]
        error_status = 0
        error_index = 0
        results: list[tuple[tuple[int, ...], object, Optional[int]]] = []

        if pdu_type == PDU_GET:
            for position, oid in enumerate(oids, start=1):
                if oid in self.mib:
                    results.append((oid, self.mib[oid], None))
                elif version == 0:  # SNMPv1 has no per-varbind exception
                    error_status, error_index = ERR_NO_SUCH_NAME, position
                    results = [(oid, None, TAG_NULL) for oid in oids]
                    break
                else:
                    results.append((oid, None, 0x80))  # noSuchObject

        elif pdu_type == PDU_GET_NEXT:
            for oid in oids:
                nxt = self._next(oid)
                if nxt is None:
                    if version == 0:
                        error_status, error_index = ERR_NO_SUCH_NAME, 1
                        results = [(oid, None, TAG_NULL)]
                        break
                    results.append((oid, None, TAG_END_OF_MIB_VIEW))
                else:
                    results.append((nxt, self.mib[nxt], None))

        elif pdu_type == PDU_GET_BULK:
            # In a GETBULK the error-status/error-index slots carry
            # non-repeaters (field2, unused here) and max-repetitions.
            max_repetitions = field3
            for oid in oids:
                cursor = oid
                for _ in range(max(1, max_repetitions)):
                    nxt = self._next(cursor)
                    if nxt is None:
                        results.append((cursor, None, TAG_END_OF_MIB_VIEW))
                        break
                    results.append((nxt, self.mib[nxt], None))
                    cursor = nxt
        else:
            return None

        return self._build_response(version, request_id, error_status, error_index, results)

    def _next(self, oid: tuple[int, ...]) -> Optional[tuple[int, ...]]:
        for candidate in self.order:
            if candidate > oid:
                return candidate
        return None

    def _build_response(
        self,
        version: int,
        request_id: int,
        error_status: int,
        error_index: int,
        results: list[tuple[tuple[int, ...], object, Optional[int]]],
    ) -> bytes:
        varbinds = b"".join(
            _tlv(TAG_SEQUENCE, _enc_oid(oid) + _encode_value(value, tag))
            for oid, value, tag in results
        )
        pdu_body = (
            _enc_int(request_id)
            + _enc_int(error_status)
            + _enc_int(error_index)
            + _tlv(TAG_SEQUENCE, varbinds)
        )
        pdu = _tlv(PDU_RESPONSE, pdu_body)
        return _tlv(
            TAG_SEQUENCE, _enc_int(version) + _enc_octets(self.community) + pdu
        )


def _encode_value(value: object, forced_tag: Optional[int]) -> bytes:
    if forced_tag is not None:
        return _tlv(forced_tag, b"")
    if isinstance(value, bool):
        return _enc_int(int(value))
    if isinstance(value, int):
        return _enc_int(value)
    if isinstance(value, bytes):
        return _tlv(TAG_OCTET_STRING, value)
    if value is None:
        return _tlv(TAG_NULL, b"")
    return _enc_octets(str(value))


# Keep the imports honest for linters that check usage.
_ = (TAG_INTEGER, _dec_tlv)
