# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

import os
import logging
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import duckdb
from app.core.stores.tabular.base_tabular_store import BaseTabularStore

logger = logging.getLogger(__name__)


class DuckDBTabularStore(BaseTabularStore):
    """
    DuckDB-based tabular store.

    Provides methods to save, load, list and inspect tabular data stored in DuckDB.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
         # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"🗄️ DuckDBTabularStore initialized at {self.db_path}")

    def save_table(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Save a pandas DataFrame to DuckDB under the specified table name.
        Overwrites existing table if it exists.
        """
        try:
            with duckdb.connect(str(self.db_path)) as con:
                con.register("df_view", df)
                con.execute(f"DROP TABLE IF EXISTS {table_name}")
                con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_view")
            logger.info(f"✅ Saved table '{table_name}' to {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save table '{table_name}': {e}", exc_info=True)
            raise

    def load_table(self, table_name: str) -> pd.DataFrame:
        """
        Load a DuckDB table into a pandas DataFrame.
        """
        try:
            with duckdb.connect(str(self.db_path)) as con:
                df = con.execute(f"SELECT * FROM {table_name}").df()
            logger.info(f"✅ Loaded table '{table_name}' from {self.db_path}")
            return df
        except Exception as e:
            logger.error(f"❌ Failed to load table '{table_name}': {e}", exc_info=True)
            raise


    def delete_table(self, document_name: str) -> None:
        """
        Deletes the DuckDB table for the given document UID if it exists,
        after checking explicitly for its existence.
        """
        document_name = os.path.splitext(document_name)[0]
        try:
            with duckdb.connect(str(self.db_path)) as con:
                # Vérifier si la table existe
                result = con.execute("SHOW TABLES").fetchall()
                tables = [row[0] for row in result]

                if document_name in tables:
                    con.execute(f'DROP TABLE "{document_name}"')
                    logger.info(f"🗑️ Deleted DuckDB table '{document_name}' from {self.db_path}")
                    self.list_tables()
                else:
                    logger.info(f"ℹ️ DuckDB table '{document_name}' does not exist in {self.db_path}, nothing to delete.")
        except Exception as e:
            logger.error(f"❌ Failed to delete DuckDB table '{document_name}': {e}", exc_info=True)
            raise



    def list_tables(self) -> List[str]:
        """
        List all tables in the DuckDB database.
        """
        try:
            with duckdb.connect(str(self.db_path)) as con:
                result = con.execute("SHOW TABLES").fetchall()
            tables = [row[0] for row in result]
            logger.info(f"📋 Tables in {self.db_path}: {tables}")
            return tables
        except Exception as e:
            logger.error(f"❌ Failed to list tables: {e}", exc_info=True)
            raise

    def get_table_schema(self, table_name: str) -> List[Tuple[str, str]]:
        """
        Get the schema of a DuckDB table as a list of (column_name, type) tuples.
        """
        try:
            with duckdb.connect(str(self.db_path)) as con:
                df = con.execute(f"PRAGMA table_info('{table_name}')").df()
            schema = list(zip(df["name"], df["type"]))
            logger.info(f"📋 Schema for table '{table_name}': {schema}")
            return schema
        except Exception as e:
            logger.error(f"❌ Failed to get schema for table '{table_name}': {e}", exc_info=True)
            raise
    
    def execute_sql_query(self, sql: str) -> pd.DataFrame:
        """
        Execute an arbitrary SQL query and return the result as a pandas DataFrame.
        """
        try:
            with duckdb.connect(str(self.db_path)) as con:
                df = con.execute(sql).df()
            logger.info(f"✅ Executed SQL query successfully.")
            return df
        except Exception as e:
            logger.error(f"❌ Failed to execute SQL query: {e}", exc_info=True)
            raise
