"""The license server.

A small stdlib HTTP server the vendor runs (any $5 VPS will do — put it
behind a reverse proxy for TLS). The POS talks to three endpoints:

    POST /v1/activate     {license_key, fingerprint, hostname, eula_version,
                           eula_accepted}
    POST /v1/heartbeat    {license_key, fingerprint}
    POST /v1/deactivate   {license_key, fingerprint}

Activation requires ``eula_accepted: true`` — the accepted EULA version is
recorded with the activation, which is the vendor's evidence of clickwrap
assent. Activate and heartbeat both return a fresh signed token; heartbeat
is refused (403) once a key is revoked or its seat has been released
server-side, which is how a pulled license actually shuts the app off:
the last token it got simply runs out.

Admin actions (issue / revoke / release seats) happen through the
``pos-license`` CLI on the same box, against the same database.
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ed25519, tokens
from .store import SeatLimitReached, Store

DEFAULT_PORT = 8722
TOKEN_TTL = 72 * 3600  # offline grace period: 3 days

SIGNING_KEY_FILE = "signing.key"
PUBLIC_KEY_FILE = "verify.pub"
DB_FILE = "licenses.db"


def init_data_dir(data_dir: str | Path) -> Path:
    """Create the server data directory with a fresh signing keypair."""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    key_path = root / SIGNING_KEY_FILE
    if key_path.exists():
        raise FileExistsError(f"{key_path} already exists; refusing to overwrite")
    sk = ed25519.create_signing_key()
    key_path.write_bytes(sk.hex().encode("ascii") + b"\n")
    key_path.chmod(0o600)
    (root / PUBLIC_KEY_FILE).write_bytes(
        ed25519.publickey(sk).hex().encode("ascii") + b"\n"
    )
    Store(root / DB_FILE).close()
    return root


def load_signing_key(data_dir: str | Path) -> bytes:
    return bytes.fromhex((Path(data_dir) / SIGNING_KEY_FILE).read_text().strip())


def load_public_key(data_dir: str | Path) -> bytes:
    return bytes.fromhex((Path(data_dir) / PUBLIC_KEY_FILE).read_text().strip())


class _Handler(BaseHTTPRequestHandler):
    server_version = "FenixLicense/1.0"
    store: Store
    signing_key: bytes
    token_ttl: int

    # -- plumbing ----------------------------------------------------------

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64 * 1024:
                return None
            data = json.loads(self.rfile.read(length))
            return data if isinstance(data, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def log_message(self, fmt: str, *args) -> None:  # quiet default logging
        pass

    # -- routes ------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        routes = {
            "/v1/activate": self._activate,
            "/v1/heartbeat": self._heartbeat,
            "/v1/deactivate": self._deactivate,
        }
        handler = routes.get(self.path)
        if handler is None:
            self._reply(404, {"error": "not_found"})
            return
        body = self._read_json()
        if body is None:
            self._reply(400, {"error": "bad_request"})
            return
        try:
            handler(body)
        except Exception:  # never let one request kill the worker
            self._reply(500, {"error": "internal"})

    def _lookup(self, body: dict):
        """Resolve and validate the license named in the request.

        Returns (license, fingerprint) or None after replying with an error.
        """
        key = str(body.get("license_key", ""))
        fp = str(body.get("fingerprint", ""))
        if not key or not fp or len(fp) > 64:
            self._reply(400, {"error": "bad_request"})
            return None
        lic = self.store.find_by_key(key)
        if lic is None:
            self._reply(404, {"error": "unknown_key",
                              "detail": "license key not recognized"})
            return None
        if lic.revoked:
            self._reply(403, {"error": "revoked", "detail": lic.revoke_reason})
            return None
        return lic, fp

    def _issue_token(self, lic, fp: str) -> str:
        now = int(time.time())
        payload = tokens.TokenPayload(
            key_id=lic.key_id,
            fingerprint=fp,
            customer=lic.customer,
            issued_at=now,
            expires_at=now + self.token_ttl,
        )
        return tokens.issue(payload, self.signing_key)

    def _activate(self, body: dict) -> None:
        found = self._lookup(body)
        if found is None:
            return
        lic, fp = found
        if not body.get("eula_accepted"):
            self._reply(403, {"error": "eula_not_accepted",
                              "detail": "the license agreement must be "
                                        "accepted before activation"})
            return
        try:
            self.store.activate(
                lic, fp,
                hostname=str(body.get("hostname", ""))[:120],
                eula_version=str(body.get("eula_version", ""))[:40],
            )
        except SeatLimitReached as exc:
            self._reply(409, {
                "error": "seat_limit",
                "detail": str(exc),
                "active_on": [a.hostname for a in exc.holders],
            })
            return
        self._reply(200, {"token": self._issue_token(lic, fp)})

    def _heartbeat(self, body: dict) -> None:
        found = self._lookup(body)
        if found is None:
            return
        lic, fp = found
        if self.store.get_activation(lic.key_id, fp) is None:
            # Seat was released server-side (or never activated): the POS
            # must go through activation again.
            self._reply(403, {"error": "not_activated",
                              "detail": "this machine no longer holds a seat"})
            return
        self.store.touch(lic.key_id, fp)
        self._reply(200, {"token": self._issue_token(lic, fp)})

    def _deactivate(self, body: dict) -> None:
        found = self._lookup(body)
        if found is None:
            return
        released = self.store.deactivate(found[0].key_id, found[1])
        self._reply(200, {"released": released})


def make_server(data_dir: str | Path, host: str = "0.0.0.0",
                port: int = DEFAULT_PORT,
                token_ttl: int = TOKEN_TTL) -> ThreadingHTTPServer:
    root = Path(data_dir)
    handler = type("Handler", (_Handler,), {
        "store": Store(root / DB_FILE),
        "signing_key": load_signing_key(root),
        "token_ttl": token_ttl,
    })
    return ThreadingHTTPServer((host, port), handler)


def serve(data_dir: str | Path, host: str = "0.0.0.0",
          port: int = DEFAULT_PORT, token_ttl: int = TOKEN_TTL) -> None:
    httpd = make_server(data_dir, host, port, token_ttl)
    print(f"license server listening on {host}:{port}")
    print(f"public key: {load_public_key(data_dir).hex()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
