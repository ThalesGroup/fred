# agentic_backend/core/session/stores/duckdb_session_storage.py

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore

from agentic_backend.core.chatbot.chat_schema import SessionSchema
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore

logger = logging.getLogger(__name__)


def _to_iso_utc(dt: datetime | str) -> str:
    """
    Normalize to ISO-8601 in UTC with 'Z'.
    Accepts datetime or already-serialized string.
    """
    if isinstance(dt, str):
        # Assume it's already ISO-ish; keep as-is.
        return dt
    # Ensure timezone-aware UTC, then emit Z-suffixed string
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DuckdbSessionStore(BaseSessionStore):
    def __init__(self, db_path: Path):
        self.store = DuckDBTableStore(prefix="session_", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    updated_at TEXT,
                    agent_name TEXT,
                    preferences TEXT,
                    next_rank INTEGER
                )
            """)
            # Backward-compatible migrations for older tables
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info('sessions')").fetchall()
            }
            if "agent_name" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN agent_name TEXT")
            if "preferences" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN preferences TEXT")
            if "next_rank" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN next_rank INTEGER")
            # Optional index for faster list-by-user
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_updated ON sessions(user_id, updated_at)"
            )

    def save(self, session: SessionSchema) -> None:
        prefs_json = None
        if session.preferences:
            try:
                prefs_json = json.dumps(session.preferences, default=str)
            except Exception:
                prefs_json = str(session.preferences)
        with self.store._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, user_id, title, updated_at, agent_name, preferences, next_rank) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.user_id,
                    session.title,
                    _to_iso_utc(session.updated_at),  # <- always store ISO UTC text
                    session.agent_name,
                    prefs_json,
                    session.next_rank,
                ),
            )

    def get_for_user(self, user_id: str) -> List[SessionSchema]:
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, title, updated_at, agent_name, preferences, next_rank "
                "FROM sessions WHERE user_id = ? "
                "ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        sessions: List[SessionSchema] = []
        for r in rows:
            prefs = None
            if r[5]:
                try:
                    prefs = json.loads(r[5])
                except Exception:
                    prefs = None
            sessions.append(
                SessionSchema(
                    id=r[0],
                    user_id=r[1],
                    title=r[2],
                    updated_at=r[3],  # Pydantic parses ISO strings
                    agent_name=r[4],
                    preferences=prefs,
                    next_rank=r[6],
                )
            )
        return sessions

    def get(self, session_id: str) -> Optional[SessionSchema]:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, title, updated_at, agent_name, preferences, next_rank FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        prefs = None
        if row[5]:
            try:
                prefs = json.loads(row[5])
            except Exception:
                prefs = None
        return SessionSchema(
            id=row[0],
            user_id=row[1],
            title=row[2],
            updated_at=row[3],
            agent_name=row[4],
            preferences=prefs,
            next_rank=row[6],
        )

    def delete(self, session_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
