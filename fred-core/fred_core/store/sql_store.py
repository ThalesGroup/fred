import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
import logging
from typing import List, Tuple
import tempfile
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class SQLTableStore:
    def __init__(self, driver: str, path: Path):
        self.driver = driver
        self.path = path
        if driver in ("sqlite", "duckdb"):
            self.dsn = f"{self.driver}:////{self.path}"
        else:
            self.dsn = f"{self.driver}://{self.path}"
        self.engine = create_engine(self.dsn)

        self._test_connection()

    def _test_connection(self):
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"Successfully connected to the SQL database : {self.engine.url.database}")

        except OperationalError as oe:
            msg = (
                f"\n❌ Could not connect to the database.\n"
                f"🔗 URI: {self.dsn}\n"
                f"💥 Error: {oe.orig}\n"
                f"📌 Check that:\n"
                f"  - The database server is running\n"
                f"  - The host/port is correct\n"
                f"  - Credentials are valid\n"
                f"  - The database exists\n"
            )
            logger.error(msg)
            raise RuntimeError(msg) from oe

        except SQLAlchemyError as e:
            msg = (
                f"\n❌ Unexpected error while connecting to the database.\n"
                f"🔗 URI: {self.dsn}\n"
                f"💥 Error: {str(e)}"
            )
            logger.error(msg)
            raise RuntimeError(msg) from e

    def save_table(self, table_name: str, df: pd.DataFrame):
        df.to_sql(table_name, self.engine, if_exists="replace", index=False)
        logger.info(f"Saved table '{table_name}' to SQL database")

    def load_table(self, table_name: str) -> pd.DataFrame:
        return pd.read_sql_table(table_name, self.engine)

    def delete_table(self, table_name: str):
        with self.engine.connect() as conn:
            conn.execute(sqlalchemy.text(f"DROP TABLE IF EXISTS {table_name}"))
            logger.info(f"Deleted table '{table_name}'")

    def list_tables(self) -> List[str]:
        inspector = sqlalchemy.inspect(self.engine)
        return [t for t in inspector.get_table_names()]

    def get_table_schema(self, table_name: str) -> List[Tuple[str, str]]:
        with self.engine.connect() as conn:
            result = conn.execute(sqlalchemy.text(f"SELECT * FROM {table_name} LIMIT 0"))
            return [(col, str(dtype)) for col, dtype in zip(result.keys(), result.cursor.description)]

    def execute_sql_query(self, sql: str) -> pd.DataFrame:
        return pd.read_sql(sqlalchemy.text(sql), self.engine)

def create_empty_duckdb_store() -> SQLTableStore:
    db_path = Path(tempfile.gettempdir()) / "empty_fallback.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not db_path.exists():
        db_path.touch()
        logger.info(f"✅ Created empty DuckDB file at {db_path}")

    clean_path = str(db_path).lstrip("/")
    logger.warning(f"⚠️ Using an empty fallback DuckDB SQLTableStore with path: {clean_path}")
    return SQLTableStore(driver="duckdb",path=clean_path)