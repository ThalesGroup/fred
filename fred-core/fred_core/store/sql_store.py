import pandas as pd
from sqlalchemy import create_engine, text, Table, MetaData, select, inspect
from sqlalchemy.exc import SQLAlchemyError, OperationalError
import logging
from typing import List, Tuple
import tempfile
from pathlib import Path
import sqlparse
import duckdb

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

    def _validate_table_name(self, table_name: str):
        """Vérifie que la table existe réellement dans la DB."""
        valid_tables = inspect(self.engine).get_table_names()
        if table_name not in valid_tables:
            raise ValueError(f"Invalid or unauthorized table name: {table_name}")

    def save_table(self, table_name: str, df: pd.DataFrame):
        df.to_sql(table_name, self.engine, if_exists="replace", index=False)
        logger.info(f"Saved table '{table_name}' to SQL database")

    def load_table(self, table_name: str) -> pd.DataFrame:
        self._validate_table_name(table_name)
        return pd.read_sql_table(table_name, self.engine)

    def delete_table(self, table_name: str):
        self._validate_table_name(table_name)
        with self.engine.connect() as conn:
            # On quote le nom pour éviter injection
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
            logger.info(f"Deleted table '{table_name}'")

    def list_tables(self) -> List[str]:
        return inspect(self.engine).get_table_names()

    def get_table_schema(self, table_name: str) -> List[Tuple[str, str]]:
        self._validate_table_name(table_name)
        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=self.engine)
        with self.engine.connect() as conn:
            result = conn.execute(select(table).limit(0))
            return [(col, str(dtype)) for col, dtype in zip(result.keys(), result.cursor.description)]

    def execute_sql_query(self, sql: str) -> pd.DataFrame:
        """Exécute une requête SQL générée par un LLM avec validation basique."""
        # Extraction des noms de tables de la requête
        parsed = sqlparse.parse(sql)
        tokens = [t for t in parsed[0].tokens if not t.is_whitespace]
        valid_tables = set(self.list_tables())

        # Vérification simple : la requête ne doit contenir que des tables autorisées
        for token in tokens:
            token_val = token.value.strip('"')
            if token.ttype is None and token_val in valid_tables:
                continue
            # Si le token ressemble à un nom de table mais n'est pas valide
            if token.ttype is None and token_val not in valid_tables:
                raise ValueError(f"Unauthorized table in query: {token_val}")

        return pd.read_sql(text(sql), self.engine)

def create_empty_duckdb_store() -> SQLTableStore:
    db_path = (Path(tempfile.gettempdir()) / "empty_fallback.duckdb").resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        logger.info(f"Creating new DuckDB file at {db_path}")
        duckdb.connect(db_path).close()

    logger.warning(f"Using an empty fallback DuckDB SQLTableStore with path: {db_path}")
    return SQLTableStore(driver="duckdb", path=db_path)
