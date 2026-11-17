from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class WatermarkRecord:
    payload_id: str
    owner_id: int
    label: str
    created_at: datetime
    params_fp: str


class Repository:
    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._migrate()

    def _migrate(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    payload_id TEXT PRIMARY KEY,
                    owner_id   INTEGER NOT NULL,
                    label      TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    params_fp  TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_records_owner ON records(owner_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS user_prefs (
                    user_id INTEGER PRIMARY KEY,
                    visible_watermark INTEGER NOT NULL
                );
                """
            )
            self._db.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            self._db.commit()

    # ------------------------------------------------------------------ records
    def add_record(self, record: WatermarkRecord) -> bool:
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO records(payload_id, owner_id, label, created_at, params_fp) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (record.payload_id, record.owner_id, record.label,
                     record.created_at.astimezone(timezone.utc).isoformat(), record.params_fp),
                )
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_record(self, payload_id: str) -> WatermarkRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM records WHERE payload_id = ?", (payload_id,)
            ).fetchone()
        return self._to_record(row) if row else None

    def list_records(self, owner_id: int, limit: int = 10) -> list[WatermarkRecord]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM records WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
        return [self._to_record(r) for r in rows]

    @staticmethod
    def _to_record(row: sqlite3.Row) -> WatermarkRecord:
        return WatermarkRecord(
            payload_id=row["payload_id"], owner_id=row["owner_id"], label=row["label"],
            created_at=datetime.fromisoformat(row["created_at"]), params_fp=row["params_fp"],
        )

    # ------------------------------------------------------------------ prefs
    def get_visible_pref(self, user_id: int) -> bool | None:
        with self._lock:
            row = self._db.execute(
                "SELECT visible_watermark FROM user_prefs WHERE user_id = ?", (user_id,)
            ).fetchone()
        return None if row is None else bool(row[0])

    def set_visible_pref(self, user_id: int, value: bool) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO user_prefs(user_id, visible_watermark) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET visible_watermark = excluded.visible_watermark",
                (user_id, int(value)),
            )
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()
