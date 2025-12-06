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

# agentic_backend/core/feedback/store/duckdb_feedback_store.py

# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

import logging
from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore

from agentic_backend.core.feedback.feedback_structures import FeedbackRecord
from agentic_backend.core.feedback.store.base_feedback_store import BaseFeedbackStore

logger = logging.getLogger(__name__)


class DuckdbFeedbackStore(BaseFeedbackStore):
    def __init__(self, db_path: Path):
        self.table_name = "feedback"
        self.store = DuckDBTableStore(prefix="feedback_", db_path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.store._prefixed(self.table_name)} (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    message_id TEXT,
                    agent_id TEXT,
                    rating INTEGER,
                    comment TEXT,
                    created_at TIMESTAMP,
                    user_id TEXT
                )
            """)

    def list(self) -> List[FeedbackRecord]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT * FROM "{self.store._prefixed(self.table_name)}" ORDER BY created_at DESC'
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, feedback_id: str) -> Optional[FeedbackRecord]:
        with self.store._connect() as conn:
            row = conn.execute(
                f'SELECT * FROM "{self.store._prefixed(self.table_name)}" WHERE id = ?',
                (feedback_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def save(self, feedback: FeedbackRecord) -> None:
        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.store._prefixed(self.table_name)} (
                    id, session_id, message_id, agent_id, rating,
                    comment, created_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.id,
                    feedback.session_id,
                    feedback.message_id,
                    feedback.agent_id,
                    feedback.rating,
                    feedback.comment,
                    feedback.created_at.isoformat(),
                    feedback.user_id,
                ),
            )
        logger.info(f"✅ Feedback entry '{feedback.id}' saved to DuckDB")

    def delete(self, feedback_id: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(
                f'DELETE FROM "{self.store._prefixed(self.table_name)}" WHERE id = ?',
                (feedback_id,),
            )
        if result.rowcount > 0:
            logger.info(f"🗑️ Feedback entry '{feedback_id}' deleted from DuckDB")

    def _row_to_record(self, row) -> FeedbackRecord:
        return FeedbackRecord(
            id=row[0],
            session_id=row[1],
            message_id=row[2],
            agent_id=row[3],
            rating=row[4],
            comment=row[5],
            created_at=row[6],
            user_id=row[7],
        )
