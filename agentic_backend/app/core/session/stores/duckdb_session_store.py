# app/core/session/stores/duckdb_session_storage.py

import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from app.core.chatbot.chat_schema import SessionSchema
from app.core.session.stores.base_session_store import BaseSessionStore
from fred_core.store.duckdb_store import DuckDBTableStore

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
                    updated_at TEXT
                )
            """)
            # Optional index for faster list-by-user
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_updated ON sessions(user_id, updated_at)"
            )

    def save(self, session: SessionSchema) -> None:
        with self.store._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, user_id, title, updated_at) VALUES (?, ?, ?, ?)",
                (
                    session.id,
                    session.user_id,
                    session.title,
                    _to_iso_utc(session.updated_at),  # <- always store ISO UTC text
                ),
            )

    def get_for_user(self, user_id: str) -> List[SessionSchema]:
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, title, updated_at "
                "FROM sessions WHERE user_id = ? "
                "ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        # Pydantic will parse ISO strings into datetime for updated_at
        return [
            SessionSchema(id=r[0], user_id=r[1], title=r[2], updated_at=r[3])
            for r in rows
        ]

    def get(self, session_id: str) -> Optional[SessionSchema]:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, title, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return SessionSchema(id=row[0], user_id=row[1], title=row[2], updated_at=row[3])

    def delete(self, session_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
