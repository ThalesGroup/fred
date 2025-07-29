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
import duckdb
import logging

from app.core.processors.input.common.base_input_processor import BaseTabularProcessor

logger = logging.getLogger(__name__)

class DuckDBProcessor(BaseTabularProcessor):
    """
    Input processor for DuckDB dump files (.duckdb).
    Inspects the file to extract basic metadata.
    """

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".duckdb" and file_path.is_file()

    def extract_file_metadata(self, file_path: Path) -> dict:
        con = duckdb.connect(str(file_path))
        tables = con.execute("SHOW TABLES").fetchall()
        total_rows = 0
        all_columns = set()

        for (table_name,) in tables:
            try:
                df = con.execute(f"SELECT * FROM {table_name} LIMIT 5").fetchdf()
                row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                total_rows += row_count
                all_columns.update(df.columns.tolist())
            except Exception:
                continue

        return {
            "suffix": "DUCKDB",
            "row_count": total_rows,
            "num_tables": len(tables),
            "sample_columns": list(all_columns),
        }

    def convert_file_to_table(self, file_path: Path) -> dict:
        """
        Load all tables in the .duckdb file and return a dictionary of DataFrames.
        Keys are table names.
        """
        con = duckdb.connect(str(file_path))
        tables = con.execute("SHOW TABLES").fetchall()

        result = {}
        for (table_name,) in tables:
            try:
                df = con.execute(f"SELECT * FROM {table_name}").fetchdf()
                result[table_name] = df
            except Exception as e:
                logger.warning(f"Failed to load table {table_name}: {e}")
                continue

        return result

