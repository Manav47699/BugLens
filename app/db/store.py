"""
SQLite persistence — zero extra dependencies (uses stdlib sqlite3).

Two tables:
  sessions  — full Session JSON, keyed by session.id
  reports   — full DebugReport JSON, keyed by report.id

Both are stored as JSON blobs so the schema never needs migration
while the project is still evolving.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_DB_PATH: Path = settings.workspace_dir / "buglens.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create tables if they don't exist. Call once at startup."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id   TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id         TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                data       TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reports_session
                ON reports(session_id);
        """)
    log.info(f"SQLite DB ready at {_DB_PATH}")


# ── Sessions ──────────────────────────────────────────────────────────

def save_session(session) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO sessions (id, data) VALUES (?, ?)",
            (session.id, session.model_dump_json()),
        )


def load_session(session_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT data FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return json.loads(row["data"]) if row else None


# ── Reports ───────────────────────────────────────────────────────────

def save_report(report) -> None:
    with _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO reports (id, session_id, data, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                report.id,
                report.session_id,
                report.model_dump_json(),
                report.created_at.isoformat(),
            ),
        )
    log.info(f"Report {report.id} saved to SQLite.")


def load_report(report_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT data FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
    return json.loads(row["data"]) if row else None


def list_reports() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT data FROM reports ORDER BY created_at DESC"
        ).fetchall()
    return [json.loads(r["data"]) for r in rows]