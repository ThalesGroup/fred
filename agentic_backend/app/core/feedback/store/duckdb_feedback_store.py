# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import List, Optional, Dict
from pathlib import Path
from datetime import datetime
import logging

from app.core.feedback.store.base_feedback_store import BaseFeedbackStore
from fred_core.store.duckdb_store import DuckDBTableStore

logger = logging.getLogger(__name__)


class DuckdbFeedbackStore(BaseFeedbackStore):
    def __init__(self, db_path: Path):
        self.table_name = "feedback"
        self.store = DuckDBTableStore(prefix="", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.store._prefixed(self.table_name)} (
                    id TEXT PRIMARY KEY,
                    rating INTEGER,
                    comment TEXT,
                    message_id TEXT,
                    session_id TEXT,
                    agent_name TEXT,
                    created_at TIMESTAMP
                )
            """)

    def list(self) -> List[Dict]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.store._prefixed(self.table_name)} ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get(self, feedback_id: str) -> Optional[Dict]:
        with self.store._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.store._prefixed(self.table_name)} WHERE id = ?",
                (feedback_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def save(self, feedback: Dict) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.store._prefixed(self.table_name)} (
                    id, rating, comment, message_id, session_id, agent_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback["id"],
                    feedback["rating"],
                    feedback.get("comment"),
                    feedback["messageId"],
                    feedback["sessionId"],
                    feedback["agentName"],
                    feedback.get("created_at", datetime.utcnow().isoformat()),
                ),
            )
        logger.info(f"✅ Feedback entry '{feedback['id']}' saved to DuckDB")

    def delete(self, feedback_id: str) -> bool:
        with self.store._connect() as conn:
            result = conn.execute(
                f"DELETE FROM {self.store._prefixed(self.table_name)} WHERE id = ?",
                (feedback_id,),
            )
        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"🗑️ Feedback entry '{feedback_id}' deleted from DuckDB")
        return deleted

    def _row_to_dict(self, row) -> Dict:
        return {
            "id": row[0],
            "rating": row[1],
            "comment": row[2],
            "messageId": row[3],
            "sessionId": row[4],
            "agentName": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
        }
