# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

import abc
from typing import List, Tuple
import pandas as pd


class BaseTabularStore(abc.ABC):
    """
    Abstract base class defining the interface for a tabular store.

    Any backend (e.g., DuckDB, SQLite, cloud warehouse) must implement these methods.
    """

    @abc.abstractmethod
    def save_table(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Save a pandas DataFrame to the store under the specified table name.
        """
        pass

    @abc.abstractmethod
    def load_table(self, table_name: str) -> pd.DataFrame:
        """
        Load a table from the store into a pandas DataFrame.
        """
        pass

    @abc.abstractmethod
    def delete_table(self, table_name: str) -> None:
        """
        Delete the specified table from the store.
        """
        pass

    @abc.abstractmethod
    def list_tables(self) -> List[str]:
        """
        List all tables in the store.
        """
        pass

    @abc.abstractmethod
    def get_table_schema(self, table_name: str) -> List[Tuple[str, str]]:
        """
        Get the schema of a table as a list of (column_name, type) tuples.
        """
        pass
