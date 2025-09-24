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
from typing import List, Tuple

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


class DuckDBTableStore:
    """
    General-purpose DuckDB table store with prefix-based table scoping.
    Used as a reusable base for both tabular and catalog stores.
    """

    def __init__(self, db_path: Path, prefix: str):
        self.db_path = db_path
        self.prefix = prefix
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"DuckDBTableStore ({self.prefix}) initialized at {self.db_path}")

    def _prefixed(self, table_name: str) -> str:
        if table_name.startswith(self.prefix):
            return table_name
        return f"{self.prefix}{table_name}"

    def _connect(self):
        return duckdb.connect(str(self.db_path))

    def save_table(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Save a pandas DataFrame to DuckDB under the prefixed table name.
        Overwrites existing table if it exists.
        """
        full_table = self._prefixed(table_name)
        try:
            with self._connect() as con:
                con.register("df_view", df)
                con.execute(f"DROP TABLE IF EXISTS {full_table}")
                con.execute(f"CREATE TABLE {full_table} AS SELECT * FROM df_view")
            logger.info(f"Saved table '{full_table}' to {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to save table '{full_table}': {e}", exc_info=True)
            raise

    def load_table(self, table_name: str) -> pd.DataFrame:
        """
        Load a DuckDB table into a pandas DataFrame.
        """
        full_table = self._prefixed(table_name)
        try:
            with self._connect() as con:
                df = con.execute(f'SELECT * FROM "{full_table}"').df()
            logger.info(f"Loaded table '{full_table}' from {self.db_path}")
            return df
        except Exception as e:
            logger.error(f"Failed to load table '{full_table}': {e}", exc_info=True)
            raise

    def delete_table(self, table_name: str) -> None:
        """
        Deletes the DuckDB table for the given table name if it exists,
        after checking explicitly for its existence.
        """
        full_table = self._prefixed(table_name)
        try:
            with self._connect() as con:
                result = con.execute("SHOW TABLES").fetchall()
                tables = [row[0] for row in result]
                if full_table in tables:
                    con.execute(f'DROP TABLE "{full_table}"')
                    logger.info(
                        f"Deleted DuckDB table '{full_table}' from {self.db_path}"
                    )
                else:
                    logger.info(
                        f"DuckDB table '{full_table}' does not exist in {self.db_path}, nothing to delete."
                    )
        except Exception as e:
            logger.error(
                f"Failed to delete DuckDB table '{full_table}': {e}", exc_info=True
            )
            raise

    def list_tables(self) -> List[str]:
        """
        List all tables in the DuckDB database that start with the configured prefix.
        """
        try:
            with self._connect() as con:
                result = con.execute("SHOW TABLES").fetchall()
            tables = [row[0] for row in result if row[0].startswith(self.prefix)]
            logger.info(f"{self.prefix} tables in {self.db_path}: {tables}")
            return tables
        except Exception as e:
            logger.error(f"Failed to list tables: {e}", exc_info=True)
            raise

    def get_table_schema(self, table_name: str) -> List[Tuple[str, str]]:
        """
        Get the schema of a DuckDB table as a list of (column_name, type) tuples.
        """
        full_table = self._prefixed(table_name)
        try:
            with self._connect() as con:
                df = con.execute(f"PRAGMA table_info('{full_table}')").df()
            schema = list(zip(df["name"], df["type"]))
            logger.info(f"Schema for table '{full_table}': {schema}")
            return schema
        except Exception as e:
            logger.error(
                f"Failed to get schema for table '{full_table}': {e}", exc_info=True
            )
            raise

    def execute_sql_query(self, sql: str) -> pd.DataFrame:
        """
        Execute an arbitrary SQL query and return the result as a pandas DataFrame.
        """
        try:
            with self._connect() as con:
                df = con.execute(sql).df()
            return df
        except Exception as e:
            logger.error(f"Failed to execute SQL query: {e}", exc_info=True)
            raise
