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

from pathlib import Path
from typing import List
from app.common.duckdb_store import DuckDBTableStore
from app.core.stores.metadata.base_catalog_store import PullFileEntry

class DuckdbCatalogStore:
    """
    Catalog store for pull-mode documents backed by DuckDB.
    Stores and retrieves PullFileEntry items from a catalog-prefixed table.
    """

    def __init__(self, db_path: Path):
        self.prefix = "catalog_"
        self.table_name = "pull_file"
        self.store = DuckDBTableStore(db_path, prefix=self.prefix)
        self._ensure_schema()

    def _ensure_schema(self):
        full_table = self.store._prefixed(self.table_name)
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    source_tag TEXT,
                    path TEXT,
                    size BIGINT,
                    modified_time DOUBLE,
                    hash TEXT,
                    PRIMARY KEY (source_tag, path)
                )
            """)

    def save_entries(self, source_tag: str, entries: List[PullFileEntry]):
        full_table = self.store._prefixed(self.table_name)
        with self.store._connect() as conn:
            conn.execute(f"DELETE FROM {full_table} WHERE source_tag = ?", [source_tag])
            for entry in entries:
                conn.execute(
                    f"""
                    INSERT INTO {full_table} (source_tag, path, size, modified_time, hash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        source_tag,
                        entry.path,
                        entry.size,
                        entry.modified_time,
                        entry.hash
                    ]
                )

    def list_entries(self, source_tag: str) -> List[PullFileEntry]:
        full_table = self.store._prefixed(self.table_name)
        with self.store._connect() as conn:
            result = conn.execute(
                f"""
                SELECT path, size, modified_time, hash
                FROM {full_table}
                WHERE source_tag = ?
                """,
                [source_tag]
            ).fetchall()

        return [PullFileEntry(path=r[0], size=r[1], modified_time=r[2], hash=r[3]) for r in result]
