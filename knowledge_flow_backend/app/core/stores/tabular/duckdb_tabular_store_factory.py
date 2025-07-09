# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

import logging
from pathlib import Path

from app.application_context import ApplicationContext
from app.core.stores.tabular.duckdb_tabular_store import DuckDBTabularStore

logger = logging.getLogger(__name__)


def get_tabular_store() -> DuckDBTabularStore:
    """
    Factory method that returns the appropriate TabularStore implementation
    based on the current application configuration.

    A TabularStore is responsible for persisting and retrieving **tabular datasets**
    (e.g. CSV-derived tables) in a structured database format.

    This allows:
    - Saving uploaded CSVs as SQL-like tables
    - Querying data via SQL
    - Listing available datasets
    - Inspecting schemas

    Backing implementation can vary:
    - 'duckdb' for local DuckDB-based persistence
    - other types (e.g., Postgres, cloud databases) may be added in the future

    Returns:
        An instance of DuckDBTabularStore.
    """
    config = ApplicationContext.get_instance().get_config()
    backend_type = config.tabular_storage.type  # e.g., "duckdb"

    if backend_type == "duckdb":
        duckdb_path = Path(config.tabular_storage.settings.duckdb_path).expanduser()

        # Ensure that the parent directory exists
        duckdb_path.parent.mkdir(parents=True, exist_ok=True)

        # Log initialization
        logger.info(f"✅ Using DuckDB tabular store at {duckdb_path}")

        return DuckDBTabularStore(duckdb_path)
    else:
        # Unknown backend type — this is treated as a configuration error.
        raise ValueError(f"Unsupported backend for tabular storage: {backend_type}")
