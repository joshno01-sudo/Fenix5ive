"""SQLite storage for the license server and vendor CLI.

One database file holds the issued licenses and their activations. The
same code is used by the HTTP server and by the ``pos-license`` admin CLI
running on the same box, so revoking a key at the terminal takes effect on
the very next heartbeat with no extra plumbing.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import keys

_SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
    key_id      TEXT PRIMARY KEY,
    license_key TEXT NOT NULL UNIQUE,
    customer    TEXT NOT NULL,
    email       TEXT NOT NULL DEFAULT '',
    seats       INTEGER NOT NULL DEFAULT 1,
    note        TEXT NOT NULL DEFAULT '',
    revoked     INTEGER NOT NULL DEFAULT 0,
    revoke_reason TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS activations (
    key_id       TEXT NOT NULL REFERENCES licenses(key_id),
    fingerprint  TEXT NOT NULL,
    hostname     TEXT NOT NULL DEFAULT '',
    eula_version TEXT NOT NULL DEFAULT '',
    activated_at INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL,
    PRIMARY KEY (key_id, fingerprint)
);
"""


@dataclass(frozen=True)
class License:
    key_id: str
    license_key: str
    customer: str
    email: str
    seats: int
    note: str
    revoked: bool
    revoke_reason: str
    created_at: int


@dataclass(frozen=True)
class Activation:
    key_id: str
    fingerprint: str
    hostname: str
    eula_version: str
    activated_at: int
    last_seen: int


class SeatLimitReached(Exception):
    """Every seat on the license is already bound to another machine."""

    def __init__(self, holders: list[Activation]):
        self.holders = holders
        names = ", ".join(a.hostname or a.fingerprint[:8] for a in holders)
        super().__init__(f"all seats in use (active on: {names})")


class Store:
    def __init__(self, db_path: str | Path):
        # The HTTP server handles requests on worker threads; a single
        # connection guarded by a lock is plenty at licensing traffic levels.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _commit(self) -> None:
        with self._lock:
            self._conn.commit()

    # -- licenses ----------------------------------------------------------

    def issue(self, customer: str, email: str = "", seats: int = 1,
              note: str = "") -> License:
        if seats < 1:
            raise ValueError("seats must be at least 1")
        while True:
            key = keys.generate()
            kid = keys.key_id(key)
            try:
                self._execute(
                    "INSERT INTO licenses (key_id, license_key, customer, email,"
                    " seats, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (kid, key, customer, email, seats, note, int(time.time())),
                )
                self._commit()
                return self.get(kid)  # type: ignore[return-value]
            except sqlite3.IntegrityError:
                continue  # astronomically unlikely key_id collision; reroll

    def get(self, key_id: str) -> License | None:
        row = self._execute(
            "SELECT * FROM licenses WHERE key_id = ?", (key_id,)
        ).fetchone()
        return self._license(row) if row else None

    def find_by_key(self, license_key: str) -> License | None:
        try:
            kid = keys.key_id(license_key)
        except ValueError:
            return None
        lic = self.get(kid)
        if lic and lic.license_key == keys.canonical(license_key):
            return lic
        return None

    def list_licenses(self) -> list[License]:
        rows = self._execute(
            "SELECT * FROM licenses ORDER BY created_at"
        ).fetchall()
        return [self._license(r) for r in rows]

    def set_revoked(self, key_id: str, revoked: bool, reason: str = "") -> None:
        cur = self._execute(
            "UPDATE licenses SET revoked = ?, revoke_reason = ? WHERE key_id = ?",
            (1 if revoked else 0, reason if revoked else "", key_id),
        )
        if cur.rowcount == 0:
            raise KeyError(key_id)
        self._commit()

    # -- activations -------------------------------------------------------

    def activate(self, lic: License, fingerprint: str, hostname: str = "",
                 eula_version: str = "") -> Activation:
        """Bind a machine to a seat, or refresh an existing binding.

        Raises SeatLimitReached when the license's seats are all held by
        other machines. Re-activating from the same machine is idempotent.
        """
        now = int(time.time())
        existing = self._execute(
            "SELECT * FROM activations WHERE key_id = ? AND fingerprint = ?",
            (lic.key_id, fingerprint),
        ).fetchone()
        if existing:
            self._execute(
                "UPDATE activations SET last_seen = ?, hostname = ?"
                " WHERE key_id = ? AND fingerprint = ?",
                (now, hostname or existing["hostname"], lic.key_id, fingerprint),
            )
            self._commit()
            return self.get_activation(lic.key_id, fingerprint)  # type: ignore[return-value]

        holders = self.activations(lic.key_id)
        if len(holders) >= lic.seats:
            raise SeatLimitReached(holders)

        self._execute(
            "INSERT INTO activations (key_id, fingerprint, hostname,"
            " eula_version, activated_at, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
            (lic.key_id, fingerprint, hostname, eula_version, now, now),
        )
        self._commit()
        return self.get_activation(lic.key_id, fingerprint)  # type: ignore[return-value]

    def get_activation(self, key_id: str, fingerprint: str) -> Activation | None:
        row = self._execute(
            "SELECT * FROM activations WHERE key_id = ? AND fingerprint = ?",
            (key_id, fingerprint),
        ).fetchone()
        return self._activation(row) if row else None

    def activations(self, key_id: str) -> list[Activation]:
        rows = self._execute(
            "SELECT * FROM activations WHERE key_id = ? ORDER BY activated_at",
            (key_id,),
        ).fetchall()
        return [self._activation(r) for r in rows]

    def touch(self, key_id: str, fingerprint: str) -> None:
        self._execute(
            "UPDATE activations SET last_seen = ?"
            " WHERE key_id = ? AND fingerprint = ?",
            (int(time.time()), key_id, fingerprint),
        )
        self._commit()

    def deactivate(self, key_id: str, fingerprint: str) -> bool:
        """Free one seat. Returns True if a binding was removed."""
        cur = self._execute(
            "DELETE FROM activations WHERE key_id = ? AND fingerprint = ?",
            (key_id, fingerprint),
        )
        self._commit()
        return cur.rowcount > 0

    def deactivate_all(self, key_id: str) -> int:
        """Free every seat on a license (vendor-side reset)."""
        cur = self._execute(
            "DELETE FROM activations WHERE key_id = ?", (key_id,)
        )
        self._commit()
        return cur.rowcount

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _license(row: sqlite3.Row) -> License:
        return License(
            key_id=row["key_id"],
            license_key=row["license_key"],
            customer=row["customer"],
            email=row["email"],
            seats=row["seats"],
            note=row["note"],
            revoked=bool(row["revoked"]),
            revoke_reason=row["revoke_reason"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _activation(row: sqlite3.Row) -> Activation:
        return Activation(
            key_id=row["key_id"],
            fingerprint=row["fingerprint"],
            hostname=row["hostname"],
            eula_version=row["eula_version"],
            activated_at=row["activated_at"],
            last_seen=row["last_seen"],
        )
