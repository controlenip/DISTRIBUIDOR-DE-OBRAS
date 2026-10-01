from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_cycles (
    cycle_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    projects_total INTEGER DEFAULT 0,
    designers_total INTEGER DEFAULT 0,
    suggestions_total INTEGER DEFAULT 0,
    assignments_total INTEGER DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS assignment_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    item_id TEXT NOT NULL,
    note TEXT,
    sgo TEXT,
    designer TEXT NOT NULL,
    posts INTEGER DEFAULT 0,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    reason TEXT,
    payload_json TEXT,
    UNIQUE(cycle_id, item_id),
    FOREIGN KEY(cycle_id) REFERENCES automation_cycles(cycle_id)
);

CREATE INDEX IF NOT EXISTS idx_assignment_item ON assignment_audit(item_id);
CREATE INDEX IF NOT EXISTS idx_assignment_designer ON assignment_audit(designer);
"""


class AuditStore:
    """Small SQLite audit store used by the automation worker.

    It does not replace Microsoft Lists. Its purpose is traceability and
    idempotency during automated cycles.
    """

    def __init__(self, path: str | Path = "data/automation_audit.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def start_cycle(self, cycle_id: str, started_at: datetime, source: str, mode: str, projects_total: int, designers_total: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO automation_cycles
                (cycle_id, started_at, source, mode, status, projects_total, designers_total)
                VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (cycle_id, started_at.isoformat(), source, mode, int(projects_total), int(designers_total)),
            )

    def finish_cycle(
        self,
        cycle_id: str,
        finished_at: datetime,
        status: str,
        suggestions_total: int,
        assignments_total: int,
        message: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE automation_cycles
                SET finished_at=?, status=?, suggestions_total=?, assignments_total=?, message=?
                WHERE cycle_id=?
                """,
                (finished_at.isoformat(), status, int(suggestions_total), int(assignments_total), message, cycle_id),
            )

    def log_assignment(
        self,
        cycle_id: str,
        created_at: datetime,
        row: dict,
        action: str,
        result: str,
        reason: str = "",
        payload: dict | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assignment_audit
                (cycle_id, created_at, item_id, note, sgo, designer, posts, action, result, reason, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    created_at.isoformat(),
                    str(row.get("item_id", "")),
                    None if pd.isna(row.get("Nº da nota")) else str(row.get("Nº da nota")),
                    None if pd.isna(row.get("Nota SGO")) else str(row.get("Nota SGO")),
                    str(row.get("Projetista", "")),
                    int(row.get("PLN", 0) or 0),
                    action,
                    result,
                    reason or str(row.get("Motivo", "")),
                    json.dumps(payload or {}, ensure_ascii=False, default=str),
                ),
            )

    def item_was_assigned(self, item_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM assignment_audit WHERE item_id=? AND action='assign' AND result='success' LIMIT 1",
                (str(item_id),),
            ).fetchone()
        return row is not None

    def recent_cycles(self, limit: int = 20) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM automation_cycles ORDER BY started_at DESC LIMIT ?",
                conn,
                params=(int(limit),),
            )

    def recent_assignments(self, limit: int = 100) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM assignment_audit ORDER BY created_at DESC LIMIT ?",
                conn,
                params=(int(limit),),
            )
