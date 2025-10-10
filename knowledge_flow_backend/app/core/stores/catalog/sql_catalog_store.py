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

import re
from pathlib import Path
from typing import List

from fred_core.store.sql_store import SQLTableStore
from sqlalchemy import BigInteger, Column, Float, MetaData, String, Table, delete, insert, select, update

from app.core.stores.catalog.base_catalog_store import PullFileEntry

_VALID_TABLE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _safe_table_name(name: str) -> str:
    if not _VALID_TABLE_RE.match(name):
        raise ValueError(f"Unsafe table name: {name!r}")
    return name


class SQLCatalogStore:
    def __init__(self, driver: str, db_path: Path):
        self.table_name = _safe_table_name("catalog_pull_file")
        self.store = SQLTableStore(driver=driver, path=db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        metadata = MetaData()
        Table(
            _safe_table_name(self.table_name),
            metadata,
            Column("source_tag", String, primary_key=True),
            Column("path", String, primary_key=True),
            Column("size", BigInteger),
            Column("modified_time", Float),
            Column("hash", String),
        )
        metadata.create_all(self.store.engine)

    def save_entries(self, source_tag: str, entries: List[PullFileEntry]):
        meta = MetaData()
        tbl = Table(self.table_name, meta, autoload_with=self.store.engine)

        with self.store.engine.begin() as conn:
            # Delete existing entries with this source_tag
            conn.execute(delete(tbl).where(tbl.c.source_tag == source_tag))

            # Insert all entries
            for entry in entries:
                stmt = insert(tbl).values(
                    source_tag=source_tag,
                    path=entry.path,
                    size=entry.size,
                    modified_time=entry.modified_time,
                    hash=entry.hash,
                )
                conn.execute(stmt)

    def add_entries(self, source_tag: str, entries: List[PullFileEntry]):
        meta = MetaData()
        tbl = Table(self.table_name, meta, autoload_with=self.store.engine)

        with self.store.engine.begin() as conn:
            # Fetch existing entries for source_tag
            rows = conn.execute(select(tbl.c.path, tbl.c.hash).where(tbl.c.source_tag == source_tag)).fetchall()
            existing = {row[0]: row[1] for row in rows}
            for entry in entries:
                if entry.path in existing:
                    if existing[entry.path] != entry.hash:
                        # Update changed entries
                        stmt = (
                            update(tbl)
                            .where(tbl.c.source_tag == source_tag)
                            .where(tbl.c.path == entry.path)
                            .values(
                                size=entry.size,
                                modified_time=entry.modified_time,
                                hash=entry.hash,
                            )
                        )
                        conn.execute(stmt)
                else:
                    # Insert new entries
                    stmt = insert(tbl).values(
                        source_tag=source_tag,
                        path=entry.path,
                        size=entry.size,
                        modified_time=entry.modified_time,
                        hash=entry.hash,
                    )
                    conn.execute(stmt)

    def delete_entries(self, source_tag: str, entries: List[PullFileEntry]):
        if not entries:
            return

        paths = [e.path for e in entries]
        meta = MetaData()
        tbl = Table(self.table_name, meta, autoload_with=self.store.engine)

        stmt = delete(tbl).where(tbl.c.source_tag == source_tag).where(tbl.c.path.in_(paths))
        with self.store.engine.begin() as conn:
            conn.execute(stmt)

    def list_entries(self, source_tag: str) -> List[PullFileEntry]:
        meta = MetaData()
        tbl = Table(self.table_name, meta, autoload_with=self.store.engine)

        with self.store.engine.connect() as conn:
            rows = conn.execute(select(tbl.c.path, tbl.c.size, tbl.c.modified_time, tbl.c.hash).where(tbl.c.source_tag == source_tag)).fetchall()

        return [PullFileEntry(path=r[0], size=r[1], modified_time=r[2], hash=r[3]) for r in rows]
