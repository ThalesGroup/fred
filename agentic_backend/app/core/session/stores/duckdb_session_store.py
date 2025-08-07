# app/core/session/stores/duckdb_session_storage.py

import logging
from typing import List, Optional


from app.core.session.session_manager import SessionSchema
from app.core.session.stores.base_session_store import BaseSessionStore
from fred_core.store.duckdb_store import DuckDBTableStore

logger = logging.getLogger(__name__)


class DuckdbSessionStore(BaseSessionStore):
    def __init__(self, db_path):
        self.store = DuckDBTableStore(prefix="", db_path=db_path)
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

    def save(self, session: SessionSchema) -> None:
        with self.store._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, user_id, title, updated_at) VALUES (?, ?, ?, ?)",
                (session.id, session.user_id, session.title, session.updated_at)
            )

    def get_for_user(self, user_id: str) -> List[SessionSchema]:
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, title, updated_at FROM sessions WHERE user_id = ?",
                (user_id,)
            ).fetchall()
        return [SessionSchema(id=row[0], user_id=row[1], title=row[2], updated_at=row[3]) for row in rows]

    def get(self, session_id: str) -> Optional[SessionSchema]:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, title, updated_at FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()
        if not row:
            return None
        return SessionSchema(id=row[0], user_id=row[1], title=row[2], updated_at=row[3])

    def delete(self, session_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
