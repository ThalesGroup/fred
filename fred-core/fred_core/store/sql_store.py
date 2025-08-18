import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError, OperationalError
import logging
from typing import List
import tempfile
from pathlib import Path
import sqlparse
from sqlparse.sql import Identifier, IdentifierList
from sqlparse.tokens import Keyword, Whitespace, Punctuation
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

    def get_table_schema(self, table_name):
        self._validate_table_name(table_name)
        inspector = inspect(self.engine)
        return [
            (col["name"], str(col["type"]))
            for col in inspector.get_columns(table_name)
        ]

    def _strip_quotes(self, name: str) -> str:
        return str(name).strip('"`[]')

    def _extract_tables_from_query(self, sql: str) -> set[str]:
        """Extract only table names that appear after FROM / JOIN / UPDATE / INTO.
        No recursion, so it won't blow the stack on complex queries."""
        tables: set[str] = set()

        for stmt in sqlparse.parse(sql):
            expecting = False  # expecting a table list after a keyword
            for tok in stmt.tokens:
                # Start of a table list?
                if tok.ttype is Keyword and tok.value.upper() in ("FROM", "JOIN", "UPDATE", "INTO"):
                    expecting = True
                    continue

                if not expecting:
                    continue

                # Skip noise between keyword and identifier(s)
                if tok.ttype in (Whitespace, Punctuation):
                    continue

                # Handle "FROM a, b"
                if isinstance(tok, IdentifierList):
                    for ident in tok.get_identifiers():
                        name = ident.get_real_name() or ident.get_name()
                        if name:
                            tables.add(self._strip_quotes(name))
                    expecting = False
                    continue

                # Handle "FROM schema.table AS t" or "FROM table t"
                if isinstance(tok, Identifier):
                    name = tok.get_real_name() or tok.get_name()
                    if name:
                        tables.add(self._strip_quotes(name))
                    expecting = False
                    continue

                # Anything else ends the expectation (subquery, etc.)
                expecting = False

        return tables

    def execute_sql_query(self, sql: str) -> pd.DataFrame:
        """Execute with a basic allowlist: only tables from FROM/JOIN/UPDATE/INTO are validated."""
        try:
            referenced = self._extract_tables_from_query(sql)
        except Exception as e:
            logger.warning(f"Table extraction failed ({e}). Skipping validation for this query.")
            referenced = set()

        valid = set(self.list_tables())
        unauthorized = {t for t in referenced if t not in valid}
        if unauthorized:
            raise ValueError(f"Unauthorized table(s) in query: {', '.join(sorted(unauthorized))}")

        return pd.read_sql(text(sql), self.engine)
    
def create_empty_duckdb_store() -> SQLTableStore:
    db_path = (Path(tempfile.gettempdir()) / "empty_fallback.duckdb").resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        logger.info(f"Creating new DuckDB file at {db_path}")
        duckdb.connect(db_path).close()

    logger.warning(f"Using an empty fallback DuckDB SQLTableStore with path: {db_path}")
    return SQLTableStore(driver="duckdb", path=db_path)
