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

import logging
from pathlib import Path
from app.common.document_structures import DocumentMetadata, ProcessingStage
from app.core.processors.output.base_output_processor import BaseOutputProcessor
from app.application_context import ApplicationContext
import duckdb

logger = logging.getLogger(__name__)


class DuckDBProcessor(BaseOutputProcessor):
    """
    Processor for importing tables from a .duckdb database file
    into the system's internal DuckDB store.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.tabular_store = self.context.get_tabular_store()

    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        try:
            logger.info(f"Loading DuckDB file from: {file_path}")
            db_path = Path(file_path)
            if not db_path.exists() or db_path.suffix != ".duckdb":
                raise ValueError("Invalid file type or path (must be a .duckdb file)")

            source_con = duckdb.connect(str(db_path))
            target_store = self.tabular_store
            if target_store is None:
                raise RuntimeError("tabular_store is not initialized")

            tables = source_con.execute("SHOW TABLES").fetchall()
            if not tables:
                raise ValueError("No tables found in provided .duckdb file.")

            for (table_name,) in tables:
                df = source_con.execute(f"SELECT * FROM {table_name}").fetchdf()
                target_store.save_table(table_name, df)
                logger.info(f"Imported table: {table_name} ({len(df)} rows)")

            metadata.mark_stage_done(ProcessingStage.SQL_INDEXED)
            return metadata

        except Exception as e:
            logger.exception("Failed to import .duckdb file")
            raise RuntimeError(f"Failed to import .duckdb: {e}")
