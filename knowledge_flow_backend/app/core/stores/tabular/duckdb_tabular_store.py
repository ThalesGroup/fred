# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

import os
import logging
from pathlib import Path
from typing import List, Tuple
import shutil

import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class DuckDBTabularStore:
    """
    DuckDB-based tabular store.

    Provides methods to save, load, list and inspect tabular data stored in DuckDB.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        logger.info(f"🗄️ DuckDBTabularStore initialized at {self.db_path}")

        # ⚠️ Optional: remove or comment in prod
        # self.initialize_with_test_data()

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
    
    def initialize_with_test_data(self):
        """
        Initialize the database with example 'owners' and 'devices' tables,
        including PK/FK constraints and sample data to test joins.
        """
        logger.info("⚙️ Initializing database with test data (owners + devices)...")
        
        # Sample data as DataFrames
        owners_data = {
            "owner_id": [1, 2, 3, 4, 5],
            "owner_name": [
                "Saint-Gobain",
                "LVMH",
                "BNP Paribas",
                "Airbus",
                "Sanofi"
            ]
        }
        devices_data = {
            "device_id": [101, 102, 103, 104, 105],
            "owner_id": [1, 2, 3, 1, 5],
            "device_type": ["Server", "Switch", "GPU", "Server", "CDU"],
            "location": [
                "DC1_RACK_A",
                "DC1_RACK_B",
                "DC1_RACK_C",
                "DC1_RACK_D",
                "DC1_RACK_E"
            ],
            "consumption": [400,150,300,420,200]
        }

        owners_df = pd.DataFrame(owners_data)
        devices_df = pd.DataFrame(devices_data)

        try:
            with duckdb.connect(str(self.db_path)) as con:
                # Drop existing tables if any
                con.execute("DROP TABLE IF EXISTS devices")
                con.execute("DROP TABLE IF EXISTS owners")
                
                
                # Create owners table
                con.execute("""
                    CREATE TABLE owners (
                        owner_id INTEGER PRIMARY KEY,
                        owner_name VARCHAR
                    )
                """)
                con.register("owners_view", owners_df)
                con.execute("INSERT INTO owners SELECT * FROM owners_view")
                logger.info("✅ Table 'owners' created and populated.")

                # Create devices table with FK
                con.execute("""
                    CREATE TABLE devices (
                        device_id INTEGER PRIMARY KEY,
                        owner_id INTEGER REFERENCES owners(owner_id),
                        device_type VARCHAR,
                        location VARCHAR,
                        consumption BIGINT
                    )
                """)
                con.register("devices_view", devices_df)
                con.execute("INSERT INTO devices SELECT * FROM devices_view")
                logger.info("✅ Table 'devices' created and populated.")

            logger.info("✅ Database initialized with test data successfully.")

        except Exception as e:
            logger.error(f"❌ Failed to initialize test data: {e}", exc_info=True)
            raise

