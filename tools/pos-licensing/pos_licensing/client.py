"""The client the POS embeds.

Typical integration::

    from pos_licensing.client import LicenseClient, LicenseState

    lic = LicenseClient(
        server_url="https://license.example.com",
        public_key_hex="<hex printed by `pos-license init`>",
        state_dir=APP_DATA_DIR,
        eula_version="1.0",
    )

    # First run / settings screen — after the user ticks "I agree":
    lic.activate("FNX5-XXXXX-XXXXX-XXXXX-XXXXX", eula_accepted=True)

    # Every startup, and from a timer a few times a day:
    status = lic.check()
    if not status.usable:
        show_locked_screen(status.message)   # e.g. sales disabled, data
                                             # still viewable — your call

The states, and what the POS should do with them:

============  =========================================================
ACTIVE        Licensed and current. Run normally.
GRACE         Licensed, but the license server could not be reached.
              Run normally; the cached token covers the outage (72 h by
              default). Maybe show a quiet warning near the end of it.
NOT_ACTIVATED No license on this machine yet. Show the activation screen.
EXPIRED       The cached token ran out and the server is unreachable.
              Lock the app until a heartbeat gets through.
REVOKED       The vendor pulled the license (or released this seat).
              Lock the app and show the reason.
============  =========================================================

Honest note on what this can and cannot do: any purely client-side check
can be defeated by someone determined enough with a debugger — that is
true of every licensing system ever shipped. The point is to make casual
copying (installing one paid key at a second location) fail immediately
and visibly, and to give the vendor a working kill switch. The legal
backstop for determined offenders is the license agreement itself.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import fingerprint as fp_mod
from . import keys, tokens

TOKEN_FILENAME = "license.token"
KEY_FILENAME = "license.key"
# Renew when the token has under this long left; with a 72 h TTL and a POS
# that is online most of the day, renewal happens long before expiry.
RENEW_MARGIN = 48 * 3600


class LicenseState(Enum):
    ACTIVE = "active"
    GRACE = "grace"
    NOT_ACTIVATED = "not_activated"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class LicenseStatus:
    state: LicenseState
    message: str = ""
    customer: str = ""
    expires_at: int = 0

    @property
    def usable(self) -> bool:
        return self.state in (LicenseState.ACTIVE, LicenseState.GRACE)


class ActivationError(Exception):
    """Activation was refused; .code is the server's error code."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(detail or code)


class LicenseClient:
    def __init__(self, server_url: str, public_key_hex: str,
                 state_dir: str | Path, eula_version: str = "",
                 timeout: float = 10.0):
        self._url = server_url.rstrip("/")
        self._public_key = bytes.fromhex(public_key_hex)
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._eula_version = eula_version
        self._timeout = timeout
        self._fingerprint = fp_mod.fingerprint()

    # -- public API --------------------------------------------------------

    def activate(self, license_key: str, eula_accepted: bool = False) -> LicenseStatus:
        """Claim a seat for this machine. Raises ActivationError on refusal.

        ``eula_accepted`` must reflect a real click on a real "I agree"
        checkbox — the acceptance (and the EULA version) is recorded
        server-side as evidence of assent, so never hard-code it.
        """
        if not keys.is_valid_format(license_key):
            raise ActivationError("bad_key", "that doesn't look like a valid "
                                             "license key — check for typos")
        status, body = self._post("/v1/activate", {
            "license_key": keys.canonical(license_key),
            "fingerprint": self._fingerprint,
            "hostname": fp_mod.hostname(),
            "eula_version": self._eula_version,
            "eula_accepted": bool(eula_accepted),
        })
        if status != 200:
            raise ActivationError(body.get("error", "server_error"),
                                  body.get("detail", ""))
        self._save(body["token"], keys.canonical(license_key))
        return self.check()

    def check(self) -> LicenseStatus:
        """The main gate: call at startup and periodically while running."""
        cached = self._load_token()
        if cached is None:
            return LicenseStatus(LicenseState.NOT_ACTIVATED,
                                 "no license is installed on this machine")
        try:
            payload = tokens.verify(cached, self._public_key)
        except tokens.TokenError:
            self._clear()
            return LicenseStatus(LicenseState.NOT_ACTIVATED,
                                 "the stored license is damaged — "
                                 "please activate again")
        if payload.fingerprint != self._fingerprint:
            self._clear()
            return LicenseStatus(LicenseState.NOT_ACTIVATED,
                                 "this license was activated on a different "
                                 "machine")

        now = time.time()
        needs_renewal = payload.expires_at - now < RENEW_MARGIN
        if not needs_renewal:
            return self._ok(payload)
        return self._renew(payload, expired=payload.expired(now))

    def deactivate(self) -> bool:
        """Release this machine's seat so the key can be used elsewhere."""
        license_key = self._load_key()
        released = False
        if license_key:
            try:
                status, body = self._post("/v1/deactivate", {
                    "license_key": license_key,
                    "fingerprint": self._fingerprint,
                })
                released = status == 200 and bool(body.get("released"))
            except OSError:
                pass  # offline: clear locally; the vendor can free the seat
        self._clear()
        return released

    # -- internals ---------------------------------------------------------

    def _renew(self, payload: tokens.TokenPayload, expired: bool) -> LicenseStatus:
        license_key = self._load_key()
        if not license_key:
            self._clear()
            return LicenseStatus(LicenseState.NOT_ACTIVATED,
                                 "no license is installed on this machine")
        try:
            status, body = self._post("/v1/heartbeat", {
                "license_key": license_key,
                "fingerprint": self._fingerprint,
            })
        except OSError:
            if expired:
                return LicenseStatus(
                    LicenseState.EXPIRED,
                    "the license could not be verified and the offline "
                    "period has run out — reconnect to the internet",
                    customer=payload.customer,
                    expires_at=payload.expires_at)
            return LicenseStatus(
                LicenseState.GRACE,
                "running on the cached license — the license server "
                "could not be reached",
                customer=payload.customer,
                expires_at=payload.expires_at)

        if status == 200:
            self._save(body["token"], license_key)
            fresh = tokens.verify(body["token"], self._public_key)
            return self._ok(fresh)
        if status in (403, 404):
            self._clear()
            return LicenseStatus(
                LicenseState.REVOKED,
                body.get("detail") or "this license has been deactivated "
                                      "by the vendor",
                customer=payload.customer)
        # Server misbehaving (5xx): treat like an outage.
        if expired:
            return LicenseStatus(LicenseState.EXPIRED,
                                 "license verification is unavailable",
                                 customer=payload.customer,
                                 expires_at=payload.expires_at)
        return LicenseStatus(LicenseState.GRACE,
                             "running on the cached license",
                             customer=payload.customer,
                             expires_at=payload.expires_at)

    @staticmethod
    def _ok(payload: tokens.TokenPayload) -> LicenseStatus:
        return LicenseStatus(LicenseState.ACTIVE, "licensed",
                             customer=payload.customer,
                             expires_at=payload.expires_at)

    def _post(self, path: str, body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            self._url + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            except (json.JSONDecodeError, ValueError):
                return exc.code, {}

    def _save(self, token: str, license_key: str) -> None:
        (self._dir / TOKEN_FILENAME).write_text(token, encoding="ascii")
        (self._dir / KEY_FILENAME).write_text(license_key, encoding="ascii")

    def _load_token(self) -> str | None:
        try:
            return (self._dir / TOKEN_FILENAME).read_text(encoding="ascii").strip()
        except OSError:
            return None

    def _load_key(self) -> str | None:
        try:
            return (self._dir / KEY_FILENAME).read_text(encoding="ascii").strip()
        except OSError:
            return None

    def _clear(self) -> None:
        for name in (TOKEN_FILENAME, KEY_FILENAME):
            try:
                (self._dir / name).unlink()
            except OSError:
                pass
