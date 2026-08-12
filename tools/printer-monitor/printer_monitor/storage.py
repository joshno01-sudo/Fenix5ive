"""SQLite persistence: supply history, the on-hand supply list, alert log."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

from .models import AlertEvent, PrinterReading, SupplyItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS supply_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    printer_id   TEXT    NOT NULL,
    supply_key   TEXT    NOT NULL,
    supply_name  TEXT    NOT NULL,
    percent      REAL,
    level_raw    INTEGER,
    max_capacity INTEGER,
    recorded_at  REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_lookup
    ON supply_history (printer_id, supply_key, recorded_at);

CREATE TABLE IF NOT EXISTS printer_status_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    printer_id  TEXT    NOT NULL,
    online      INTEGER NOT NULL,
    status_text TEXT,
    page_count  INTEGER,
    error       TEXT,
    recorded_at REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status_lookup
    ON printer_status_history (printer_id, recorded_at);

CREATE TABLE IF NOT EXISTS supply_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    printer_id  TEXT    NOT NULL DEFAULT '',
    part_number TEXT    NOT NULL DEFAULT '',
    category    TEXT    NOT NULL DEFAULT 'Ink',
    quantity    INTEGER NOT NULL DEFAULT 0,
    reorder_at  INTEGER NOT NULL DEFAULT 1,
    unit        TEXT    NOT NULL DEFAULT 'each',
    notes       TEXT    NOT NULL DEFAULT '',
    supply_key  TEXT    NOT NULL DEFAULT '',
    counted     INTEGER NOT NULL DEFAULT 0,
    updated_at  REAL    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_unique
    ON supply_items (printer_id, name);

CREATE TABLE IF NOT EXISTS stock_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL,
    delta      INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    reason     TEXT    NOT NULL DEFAULT '',
    changed_at REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_log_item ON stock_log (item_id, changed_at);

CREATE TABLE IF NOT EXISTS alert_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    printer_id    TEXT    NOT NULL,
    printer_name  TEXT    NOT NULL DEFAULT '',
    kind          TEXT    NOT NULL,
    subject_key   TEXT    NOT NULL,
    subject_name  TEXT    NOT NULL DEFAULT '',
    severity      TEXT    NOT NULL,
    message       TEXT    NOT NULL,
    level_percent REAL,
    threshold     REAL,
    notified_popup INTEGER NOT NULL DEFAULT 0,
    notified_email INTEGER NOT NULL DEFAULT 0,
    acknowledged  INTEGER NOT NULL DEFAULT 0,
    created_at    REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_log_created ON alert_log (created_at);

CREATE TABLE IF NOT EXISTS alert_state (
    dedupe_key    TEXT PRIMARY KEY,
    severity      TEXT NOT NULL,
    last_sent_at  REAL NOT NULL,
    last_percent  REAL
);
"""

SCHEMA_VERSION = 1


class Storage:
    """Thread-safe-enough SQLite wrapper (one connection behind a lock)."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            if not self._conn.execute("SELECT 1 FROM schema_info").fetchone():
                self._conn.execute("INSERT INTO schema_info (version) VALUES (?)", (SCHEMA_VERSION,))
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a database was first created."""
        for table, column, definition in (
            ("supply_items", "counted", "INTEGER NOT NULL DEFAULT 0"),
        ):
            existing = {
                row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                # Anything already carrying stock has plainly been counted.
                if table == "supply_items":
                    self._conn.execute(
                        "UPDATE supply_items SET counted = 1 WHERE quantity > 0"
                    )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- history -----------------------------------------------------------

    def record_reading(self, reading: PrinterReading) -> None:
        now = reading.timestamp
        rows = [
            (
                reading.printer_id,
                supply.key,
                supply.display_name,
                supply.remaining_percent,
                supply.level_raw,
                supply.max_capacity_raw,
                now,
            )
            for supply in reading.supplies
        ]
        with self._lock:
            if rows:
                self._conn.executemany(
                    "INSERT INTO supply_history "
                    "(printer_id, supply_key, supply_name, percent, level_raw, max_capacity, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            self._conn.execute(
                "INSERT INTO printer_status_history "
                "(printer_id, online, status_text, page_count, error, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    reading.printer_id,
                    1 if reading.online else 0,
                    reading.status_text,
                    reading.page_count,
                    reading.error or "",
                    now,
                ),
            )
            self._conn.commit()

    def supply_history(
        self, printer_id: str, supply_key: str, since: Optional[float] = None, limit: int = 500
    ) -> list[sqlite3.Row]:
        query = (
            "SELECT percent, recorded_at FROM supply_history "
            "WHERE printer_id = ? AND supply_key = ?"
        )
        params: list[object] = [printer_id, supply_key]
        if since is not None:
            query += " AND recorded_at >= ?"
            params.append(since)
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            return self._conn.execute(query, params).fetchall()

    def estimate_days_remaining(
        self, printer_id: str, supply_key: str, window_days: float = 30.0
    ) -> Optional[float]:
        """Straight-line burn-rate estimate from recent history.

        Ignores refills (percentage going up) by only measuring across the most
        recent continuous decline.
        """
        since = time.time() - window_days * 86400
        rows = self.supply_history(printer_id, supply_key, since=since, limit=2000)
        points = [(r["recorded_at"], r["percent"]) for r in rows if r["percent"] is not None]
        if len(points) < 2:
            return None
        points.sort(key=lambda p: p[0])  # oldest first

        # Walk back from newest to the start of the current decline.
        start_index = 0
        for i in range(len(points) - 1, 0, -1):
            if points[i][1] > points[i - 1][1] + 1.0:  # refill detected
                start_index = i
                break
        segment = points[start_index:]
        if len(segment) < 2:
            return None
        elapsed_days = (segment[-1][0] - segment[0][0]) / 86400
        drop = segment[0][1] - segment[-1][1]
        if elapsed_days <= 0 or drop <= 0:
            return None
        per_day = drop / elapsed_days
        if per_day <= 0:
            return None
        return round(segment[-1][1] / per_day, 1)

    def prune_history(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM supply_history WHERE recorded_at < ?", (cutoff,))
            removed = cur.rowcount or 0
            self._conn.execute(
                "DELETE FROM printer_status_history WHERE recorded_at < ?", (cutoff,)
            )
            self._conn.execute("DELETE FROM alert_log WHERE created_at < ?", (cutoff,))
            self._conn.commit()
        return removed

    # -- supply list (what's on the shelf) ---------------------------------

    def list_items(self, printer_id: Optional[str] = None) -> list[SupplyItem]:
        query = "SELECT * FROM supply_items"
        params: tuple = ()
        if printer_id:
            query += " WHERE printer_id = ?"
            params = (printer_id,)
        query += " ORDER BY printer_id, category, name"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [_row_to_item(row) for row in rows]

    def get_item(self, item_id: int) -> Optional[SupplyItem]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM supply_items WHERE id = ?", (item_id,)).fetchone()
        return _row_to_item(row) if row else None

    def find_item(self, printer_id: str, name: str) -> Optional[SupplyItem]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM supply_items WHERE printer_id = ? AND name = ?",
                (printer_id, name),
            ).fetchone()
        return _row_to_item(row) if row else None

    def upsert_item(self, item: SupplyItem) -> SupplyItem:
        item.updated_at = time.time()
        with self._lock:
            if item.id is None:
                existing = self._conn.execute(
                    "SELECT id FROM supply_items WHERE printer_id = ? AND name = ?",
                    (item.printer_id, item.name),
                ).fetchone()
                if existing:
                    item.id = existing["id"]
            # Carrying stock implies somebody counted it.
            counted = 1 if (item.counted or item.quantity > 0) else 0
            item.counted = bool(counted)
            if item.id is None:
                cur = self._conn.execute(
                    "INSERT INTO supply_items "
                    "(name, printer_id, part_number, category, quantity, reorder_at, unit, notes, "
                    " supply_key, counted, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.name,
                        item.printer_id,
                        item.part_number,
                        item.category,
                        item.quantity,
                        item.reorder_at,
                        item.unit,
                        item.notes,
                        item.supply_key,
                        counted,
                        item.updated_at,
                    ),
                )
                item.id = int(cur.lastrowid)
            else:
                self._conn.execute(
                    "UPDATE supply_items SET name = ?, printer_id = ?, part_number = ?, "
                    "category = ?, quantity = ?, reorder_at = ?, unit = ?, notes = ?, "
                    "supply_key = ?, counted = ?, updated_at = ? WHERE id = ?",
                    (
                        item.name,
                        item.printer_id,
                        item.part_number,
                        item.category,
                        item.quantity,
                        item.reorder_at,
                        item.unit,
                        item.notes,
                        item.supply_key,
                        counted,
                        item.updated_at,
                        item.id,
                    ),
                )
            self._conn.commit()
        return item

    def delete_item(self, item_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM supply_items WHERE id = ?", (item_id,))
            self._conn.execute("DELETE FROM stock_log WHERE item_id = ?", (item_id,))
            self._conn.commit()

    def adjust_quantity(self, item_id: int, delta: int, reason: str = "") -> Optional[SupplyItem]:
        """The +/- buttons. Clamps at zero, logs the movement, marks it counted."""
        with self._lock:
            row = self._conn.execute(
                "SELECT quantity FROM supply_items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return None
            new_quantity = max(0, int(row["quantity"]) + int(delta))
            applied = new_quantity - int(row["quantity"])
            now = time.time()
            # Touching the count at all means the shelf has been looked at, so
            # this row starts taking part in reorder alerts.
            self._conn.execute(
                "UPDATE supply_items SET quantity = ?, counted = 1, updated_at = ? WHERE id = ?",
                (new_quantity, now, item_id),
            )
            if applied:
                self._conn.execute(
                    "INSERT INTO stock_log (item_id, delta, quantity, reason, changed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (item_id, applied, new_quantity, reason, now),
                )
            self._conn.commit()
        return self.get_item(item_id)

    def set_quantity(self, item_id: int, quantity: int, reason: str = "manual set") -> Optional[SupplyItem]:
        current = self.get_item(item_id)
        if current is None:
            return None
        return self.adjust_quantity(item_id, int(quantity) - current.quantity, reason)

    def stock_log(self, item_id: int, limit: int = 50) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT delta, quantity, reason, changed_at FROM stock_log "
                "WHERE item_id = ? ORDER BY changed_at DESC LIMIT ?",
                (item_id, limit),
            ).fetchall()

    def items_needing_reorder(self) -> list[SupplyItem]:
        return [item for item in self.list_items() if item.needs_reorder]

    # -- alerts ------------------------------------------------------------

    def log_alert(self, event: AlertEvent, popup: bool, email: bool) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO alert_log (printer_id, printer_name, kind, subject_key, subject_name, "
                "severity, message, level_percent, threshold, notified_popup, notified_email, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.printer_id,
                    event.printer_name,
                    event.kind,
                    event.subject_key,
                    event.subject_name,
                    event.severity,
                    event.message,
                    event.level_percent,
                    event.threshold,
                    1 if popup else 0,
                    1 if email else 0,
                    event.timestamp,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def recent_alerts(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM alert_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()

    def unacknowledged_alert_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM alert_log WHERE acknowledged = 0"
            ).fetchone()
        return int(row["n"]) if row else 0

    def acknowledge_alerts(self, ids: Optional[Iterable[int]] = None) -> None:
        with self._lock:
            if ids is None:
                self._conn.execute("UPDATE alert_log SET acknowledged = 1")
            else:
                self._conn.executemany(
                    "UPDATE alert_log SET acknowledged = 1 WHERE id = ?",
                    [(int(i),) for i in ids],
                )
            self._conn.commit()

    # -- alert de-duplication state ---------------------------------------

    def get_alert_state(self, dedupe_key: str) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM alert_state WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()

    def set_alert_state(self, dedupe_key: str, severity: str, percent: Optional[float]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO alert_state (dedupe_key, severity, last_sent_at, last_percent) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(dedupe_key) DO UPDATE SET severity = excluded.severity, "
                "last_sent_at = excluded.last_sent_at, last_percent = excluded.last_percent",
                (dedupe_key, severity, time.time(), percent),
            )
            self._conn.commit()

    def clear_alert_state(self, dedupe_key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM alert_state WHERE dedupe_key = ?", (dedupe_key,))
            self._conn.commit()


def _row_to_item(row: sqlite3.Row) -> SupplyItem:
    return SupplyItem(
        id=row["id"],
        name=row["name"],
        printer_id=row["printer_id"],
        part_number=row["part_number"],
        category=row["category"],
        quantity=row["quantity"],
        reorder_at=row["reorder_at"],
        unit=row["unit"],
        notes=row["notes"],
        supply_key=row["supply_key"],
        counted=bool(row["counted"]),
        updated_at=row["updated_at"],
    )
