from typing import NamedTuple,Literal
from fred_core.store.sql_store import SQLTableStore

class StoreInfo(NamedTuple):
    store: SQLTableStore
    mode: Literal["read_only", "read_and_write"]