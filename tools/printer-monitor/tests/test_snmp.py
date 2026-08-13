"""SNMP codec and client tests, including a hand-computed reference packet."""

from __future__ import annotations

import pytest

from printer_monitor.snmp import (
    SnmpClient,
    SnmpTimeout,
    _build_message,
    _dec_oid,
    _enc_oid,
    _tlv,
    is_prefix,
    oid_str,
    parse_oid,
    sniff_version,
)

from .fake_agent import FakeAgent
from .mibs import LASERJET_4100, LATEX_360


# ---------------------------------------------------------------------------
# BER codec
# ---------------------------------------------------------------------------


def test_oid_round_trip():
    for text in ("1.3.6.1.2.1.1.3.0", "1.3.6.1.2.1.43.11.1.1.9.1.12", "1.3.6.1.4.1.11.2.3.9.1"):
        oid = parse_oid(text)
        tag, body, end = 0, b"", 0
        encoded = _enc_oid(oid)
        assert encoded[0] == 0x06
        assert _dec_oid(encoded[2:]) == oid
        assert oid_str(oid) == text
        del tag, body, end


def test_oid_multibyte_arcs():
    """Arcs above 127 need base-128 continuation bytes."""
    oid = parse_oid("1.3.6.1.4.1.11.2.3.9.4.2.1.1.999999")
    assert _dec_oid(_enc_oid(oid)[2:]) == oid


def test_oid_first_arc_packing():
    # 1.3.x packs to 43; 2.5.x packs to 85; 0.1.x packs to 1.
    assert _enc_oid((1, 3))[2] == 43
    assert _enc_oid((2, 5))[2] == 85
    assert _enc_oid((0, 1))[2] == 1


def test_long_length_encoding():
    payload = b"x" * 300
    encoded = _tlv(0x04, payload)
    assert encoded[0] == 0x04
    assert encoded[1] == 0x82  # two length bytes follow
    assert int.from_bytes(encoded[2:4], "big") == 300
    assert encoded[4:] == payload


def test_get_request_matches_hand_computed_packet():
    """A v2c GET of sysUpTime, request-id 1, community "public"."""
    packet = _build_message(1, "public", 0xA0, 1, [parse_oid("1.3.6.1.2.1.1.3.0")])
    expected = bytes.fromhex(
        "3026"  # SEQUENCE, 38 bytes
        "020101"  # version 1 (v2c)
        "04067075626c6963"  # community "public"
        "a019"  # GetRequest, 25 bytes
        "020101"  # request-id 1
        "020100"  # error-status 0
        "020100"  # error-index 0
        "300e"  # varbind list
        "300c"  # varbind
        "06082b06010201010300"  # OID 1.3.6.1.2.1.1.3.0
        "0500"  # NULL
    )
    assert packet == expected


def test_is_prefix():
    root = parse_oid("1.3.6.1.2.1.43.11.1.1.9")
    assert is_prefix(root, parse_oid("1.3.6.1.2.1.43.11.1.1.9.1.4"))
    assert not is_prefix(root, parse_oid("1.3.6.1.2.1.43.11.1.1.8.1.4"))
    assert is_prefix(root, root)


def test_parse_oid_accepts_leading_dot_and_sequences():
    assert parse_oid(".1.3.6.1") == (1, 3, 6, 1)
    assert parse_oid([1, 3, 6, 1]) == (1, 3, 6, 1)
    with pytest.raises(ValueError):
        parse_oid("")


# ---------------------------------------------------------------------------
# Client against the fake agent
# ---------------------------------------------------------------------------


@pytest.fixture
def latex_agent():
    with FakeAgent(LATEX_360) as agent:
        yield agent


def client_for(agent: FakeAgent, version: str = "2c", **kwargs) -> SnmpClient:
    return SnmpClient(
        host=agent.host,
        port=agent.port,
        community=agent.community,
        version=version,
        timeout=kwargs.pop("timeout", 1.5),
        retries=kwargs.pop("retries", 1),
        **kwargs,
    )


def test_get_single_value(latex_agent):
    client = client_for(latex_agent)
    assert client.get_one("1.3.6.1.2.1.43.5.1.1.16.1") == "HP Latex 360"
    assert client.get_one("1.3.6.1.2.1.1.3.0") == 918273


def test_get_missing_object_returns_default(latex_agent):
    client = client_for(latex_agent)
    assert client.get_one("1.3.6.1.2.1.99.99.99.0", default="fallback") == "fallback"


def test_get_missing_object_v1_noSuchName(latex_agent):
    """SNMPv1 signals a missing object with an error-status, not a varbind."""
    client = client_for(latex_agent, version="1")
    assert client.get_one("1.3.6.1.2.1.99.99.99.0") is None


def test_walk_column_collects_whole_table(latex_agent):
    client = client_for(latex_agent)
    levels = client.walk_column("1.3.6.1.2.1.43.11.1.1.9")
    assert levels[(1, 1)] == 5425
    assert levels[(1, 12)] == 82
    assert len(levels) == 12


def test_walk_stays_inside_its_subtree(latex_agent):
    client = client_for(latex_agent)
    descriptions = client.walk_column("1.3.6.1.2.1.43.11.1.1.6")
    assert all(isinstance(value, str) for value in descriptions.values())
    assert descriptions[(1, 1)] == "HP 831 Latex Cyan"
    assert len(descriptions) == 12


def test_walk_works_over_v1_getnext(latex_agent):
    """v1 has no GETBULK, so walk() falls back to one GETNEXT per row."""
    client = client_for(latex_agent, version="1")
    levels = client.walk_column("1.3.6.1.2.1.43.11.1.1.9")
    assert len(levels) == 12
    assert levels[(1, 4)] == 465


def test_walk_respects_limit(latex_agent):
    client = client_for(latex_agent)
    assert len(client.walk_column("1.3.6.1.2.1.43.11.1.1.9", limit=5)) == 5


def test_walk_of_empty_subtree_is_empty(latex_agent):
    client = client_for(latex_agent)
    assert client.walk_column("1.3.6.1.2.1.43.18.1.1.8") == {}


def test_bulk_batches_multiple_rows(latex_agent):
    client = client_for(latex_agent)
    batch = client.get_bulk("1.3.6.1.2.1.43.11.1.1.9.1.1", max_repetitions=4)
    assert len(batch) == 4
    assert batch[0].value == 3100  # magenta, the row after cyan


def test_timeout_when_nothing_listens():
    client = SnmpClient("127.0.0.1", port=9, timeout=0.2, retries=0)
    with pytest.raises(SnmpTimeout):
        client.get("1.3.6.1.2.1.1.3.0")
    assert client.probe() is False


def test_retry_recovers_from_a_dropped_packet():
    with FakeAgent(LATEX_360, drop_first=1) as agent:
        client = client_for(agent, retries=2, timeout=0.5)
        assert client.get_one("1.3.6.1.2.1.43.5.1.1.16.1") == "HP Latex 360"


def test_wrong_community_times_out():
    """A community mismatch looks exactly like silence, as on a real agent."""
    with FakeAgent(LATEX_360, community="private") as agent:
        client = SnmpClient(
            agent.host, port=agent.port, community="public", timeout=0.3, retries=0
        )
        assert client.probe() is False


def test_sniff_version_finds_v1_only_agent():
    """The 4100's JetDirect card is often SNMPv1-only."""
    with FakeAgent(LASERJET_4100, versions=("1",)) as agent:
        assert sniff_version(agent.host, port=agent.port, timeout=0.6) == "1"


def test_sniff_version_prefers_v2c():
    with FakeAgent(LATEX_360, versions=("1", "2c")) as agent:
        assert sniff_version(agent.host, port=agent.port, timeout=0.6) == "2c"


def test_version_normalisation():
    assert SnmpClient("h", version="v2c").version_label == "2c"
    assert SnmpClient("h", version="2c").version_label == "2c"
    assert SnmpClient("h", version=2).version_label == "2c"
    # An int 1 must mean SNMPv1 — not the on-the-wire value for v2c.
    assert SnmpClient("h", version=1).version_label == "1"
    assert SnmpClient("h", version="1").version_label == "1"
    with pytest.raises(ValueError):
        SnmpClient("h", version="3")
