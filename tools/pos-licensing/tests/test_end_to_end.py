"""End-to-end tests: real server on localhost, real client, two 'machines'."""

import threading

import pytest

from pos_licensing import server as server_mod
from pos_licensing.client import ActivationError, LicenseClient, LicenseState
from pos_licensing.store import Store


@pytest.fixture
def license_env(tmp_path):
    """Running license server + a Store handle + a client factory."""
    data_dir = tmp_path / "server"
    server_mod.init_data_dir(data_dir)

    def start(token_ttl=3600):
        httpd = server_mod.make_server(data_dir, host="127.0.0.1", port=0,
                                       token_ttl=token_ttl)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"

    def client(url, machine, eula_version="1.0"):
        c = LicenseClient(
            server_url=url,
            public_key_hex=server_mod.load_public_key(data_dir).hex(),
            state_dir=tmp_path / f"pos-{machine}",
            eula_version=eula_version,
        )
        c._fingerprint = f"{machine}-fingerprint".ljust(32, "0")
        return c

    store = Store(data_dir / server_mod.DB_FILE)
    try:
        yield start, client, store
    finally:
        store.close()


def test_single_seat_lifecycle(license_env):
    start, client, store = license_env
    httpd, url = start()
    lic = store.issue(customer="Cottage Hills Vinyl", seats=1)

    till_a = client(url, "till-a")
    till_b = client(url, "till-b")

    # First machine activates fine.
    status = till_a.activate(lic.license_key, eula_accepted=True)
    assert status.state is LicenseState.ACTIVE
    assert status.customer == "Cottage Hills Vinyl"

    # Second machine is refused: the one seat is taken.
    with pytest.raises(ActivationError) as exc:
        till_b.activate(lic.license_key, eula_accepted=True)
    assert exc.value.code == "seat_limit"
    assert not till_b.check().usable

    # Re-activating on the same machine is idempotent, not a second seat.
    assert till_a.activate(lic.license_key, eula_accepted=True).usable

    # Customer frees the seat, then the key works on the other machine.
    assert till_a.deactivate() is True
    assert till_a.check().state is LicenseState.NOT_ACTIVATED
    assert till_b.activate(lic.license_key, eula_accepted=True).usable

    httpd.shutdown(); httpd.server_close()


def test_eula_acceptance_is_required_and_recorded(license_env):
    start, client, store = license_env
    httpd, url = start()
    lic = store.issue(customer="Shop", seats=1)
    till = client(url, "till-a", eula_version="2.3")

    with pytest.raises(ActivationError) as exc:
        till.activate(lic.license_key)
    assert exc.value.code == "eula_not_accepted"

    till.activate(lic.license_key, eula_accepted=True)
    (act,) = store.activations(lic.key_id)
    assert act.eula_version == "2.3"

    httpd.shutdown(); httpd.server_close()


def test_revoke_is_a_working_kill_switch(license_env):
    start, client, store = license_env
    # Tiny TTL so every check() phones home, like a long-running POS would.
    httpd, url = start(token_ttl=60)
    lic = store.issue(customer="Shop", seats=1)
    till = client(url, "till-a")
    till.activate(lic.license_key, eula_accepted=True)

    store.set_revoked(lic.key_id, True, "additional locations unpaid")
    status = till.check()
    assert status.state is LicenseState.REVOKED
    assert "additional locations unpaid" in status.message
    # The cached token is gone: still locked even without the server.
    httpd.shutdown(); httpd.server_close()
    assert till.check().state is LicenseState.NOT_ACTIVATED

    # Reinstating lets the customer activate again.
    store.set_revoked(lic.key_id, False)
    httpd2, url2 = start(token_ttl=60)
    till2 = client(url2, "till-a")
    assert till2.activate(lic.license_key, eula_accepted=True).usable
    httpd2.shutdown(); httpd2.server_close()


def test_vendor_can_release_a_seat_remotely(license_env):
    start, client, store = license_env
    httpd, url = start(token_ttl=60)
    lic = store.issue(customer="Shop", seats=1)
    till = client(url, "till-a")
    till.activate(lic.license_key, eula_accepted=True)

    store.deactivate_all(lic.key_id)
    assert till.check().state is LicenseState.REVOKED
    # …and the seat is genuinely free for another machine.
    other = client(url, "till-b")
    assert other.activate(lic.license_key, eula_accepted=True).usable
    httpd.shutdown(); httpd.server_close()


def test_offline_grace_then_expiry(license_env):
    start, client, store = license_env

    # Token still valid + server down → GRACE (keep trading).
    httpd, url = start(token_ttl=3600)
    lic = store.issue(customer="Shop", seats=1)
    till = client(url, "till-a")
    till.activate(lic.license_key, eula_accepted=True)
    httpd.shutdown(); httpd.server_close()
    status = till.check()
    assert status.state is LicenseState.GRACE
    assert status.usable

    # Token already expired + server down → EXPIRED (locked).
    httpd2, url2 = start(token_ttl=0)
    lic2 = store.issue(customer="Shop 2", seats=1)
    till_b = client(url2, "till-b")
    till_b.activate(lic2.license_key, eula_accepted=True)
    httpd2.shutdown(); httpd2.server_close()
    assert till_b.check().state is LicenseState.EXPIRED


def test_copied_or_tampered_state_does_not_transfer(license_env):
    start, client, store = license_env
    httpd, url = start()
    lic = store.issue(customer="Shop", seats=1)
    till = client(url, "till-a")
    till.activate(lic.license_key, eula_accepted=True)

    # Copy the whole activation state to a different machine: rejected,
    # because the token is bound to till-a's fingerprint.
    thief = client(url, "till-x")
    thief._dir = till._dir
    assert thief.check().state is LicenseState.NOT_ACTIVATED

    # Tampering with the token payload breaks the signature.
    till2 = client(url, "till-a")
    till2.activate(lic.license_key, eula_accepted=True)
    token_file = till2._dir / "license.token"
    token_file.write_text("A" + token_file.read_text()[1:])
    assert till2.check().state is LicenseState.NOT_ACTIVATED
    httpd.shutdown(); httpd.server_close()
