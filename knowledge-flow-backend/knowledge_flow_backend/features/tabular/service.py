# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Dict, List, Optional, Tuple

from fred_core import Action, KeycloakUser, Resource, authorize
from fred_core.store.sql_store import SQLTableStore
from fred_core.store.structures import StoreInfo

from knowledge_flow_backend.features.tabular.structures import (
    DTypes,
    ListTableResponse,
    RawSQLRequest,
    TabularColumnSchema,
    TabularQueryResponse,
    TabularSchemaResponse,
)

logger = logging.getLogger(__name__)


class TabularService:
    """
    Service pour la gestion tabulaire multi-base.

    Désormais, un store doit être explicitement chargé via `load_store(db_name)`
    avant d'exécuter des opérations. Si aucun store n'est chargé, les méthodes
    lèvent une erreur invitant à appeler `load_store()` d'abord.
    """

    def __init__(self, stores_info: Dict[str, StoreInfo]):
        self.stores_info = stores_info
        self.loaded_store: Optional[Tuple[SQLTableStore, str]] = None

    # -------------------------------------------------------------------------
    # Gestion explicite du store
    # -------------------------------------------------------------------------

    def load_store(self, db_name: str) -> None:
        """
        Charge explicitement un store et le mémorise dans l'instance.

        :param db_name: Nom de la base à charger.
        """
        if not db_name:
            raise ValueError(f"A database name must be explicitly provided to load a store. Available databases: {list(self.stores_info.keys())}")

        if db_name not in self.stores_info:
            raise ValueError(f"Unknown database '{db_name}'. Available databases: {list(self.stores_info.keys())}")

        store = self.stores_info[db_name].store
        self.loaded_store = (store, db_name)
        logger.info(f"Store for database '{db_name}' successfully loaded.")

    def _require_store(self) -> Tuple[SQLTableStore, str]:
        """
        Vérifie qu’un store a bien été chargé avant d’exécuter une opération.
        """
        if not self.loaded_store:
            raise RuntimeError("No database is currently loaded. Please call `load_store(db_name)` before performing operations.")
        return self.loaded_store

    def _check_write_allowed(self, db_name: str):
        store_info = self.stores_info.get(db_name)
        if store_info and store_info.mode != "read_and_write":
            raise PermissionError(f"Write operations are not allowed on database '{db_name}'")

    def _sanitize_table_name(self, name: str) -> str:
        return name.replace("-", "_")

    def _map_sql_type_to_literal(self, duckdb_type: str) -> DTypes:
        duckdb_type = duckdb_type.lower()
        if any(x in duckdb_type for x in ["varchar", "string", "text"]):
            return "string"
        if "boolean" in duckdb_type:
            return "boolean"
        if any(x in duckdb_type for x in ["timestamp", "date", "time"]):
            return "datetime"
        if any(x in duckdb_type for x in ["double", "real", "float"]):
            return "float"
        if "int" in duckdb_type:
            return "integer"
        return "unknown"

    # -------------------------------------------------------------------------
    # Fonctions métiers
    # -------------------------------------------------------------------------

    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    def delete_table(self, user: KeycloakUser, table_name: str) -> None:
        store, db_name = self._require_store()
        self._check_write_allowed(db_name)
        try:
            store.delete_table(table_name)
            logger.info(f"Table '{table_name}' deleted from database '{db_name}'")
        except Exception as e:
            logger.error(f"Failed to delete table '{table_name}' from '{db_name}': {e}")
            raise

    @authorize(action=Action.READ, resource=Resource.TABLES_DATABASES)
    def list_databases(self, user: KeycloakUser) -> List[str]:
        return list(self.stores_info.keys())

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def get_schema(self, user: KeycloakUser, table_name: str) -> TabularSchemaResponse:
        store, db_name = self._require_store()
        table_name = self._sanitize_table_name(table_name)
        schema = store.get_table_schema(table_name)
        columns = [TabularColumnSchema(name=col, dtype=self._map_sql_type_to_literal(dtype)) for col, dtype in schema]
        count_df = store.execute_sql_query(f'SELECT COUNT(*) AS count FROM "{table_name}"')
        row_count = int(count_df["count"].iloc[0])
        return TabularSchemaResponse(db_name=db_name, table_name=table_name, columns=columns, row_count=row_count)

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def list_tables(self, user: KeycloakUser) -> ListTableResponse:
        store, db_name = self._require_store()
        table_names = store.list_tables()
        return ListTableResponse(db_name=db_name, tables=table_names)

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def list_tables_with_schema(self, user: KeycloakUser) -> List[TabularSchemaResponse]:
        store, db_name = self._require_store()
        responses = []
        table_names = store.list_tables()
        for table in table_names:
            try:
                schema_info = store.get_table_schema(table)
                columns = [TabularColumnSchema(name=col_name, dtype=self._map_sql_type_to_literal(col_type)) for col_name, col_type in schema_info]
                count_df = store.execute_sql_query(f'SELECT COUNT(*) AS count FROM "{table}"')
                row_count = int(count_df["count"].iloc[0])
                responses.append(
                    TabularSchemaResponse(
                        db_name=db_name,
                        table_name=table,
                        columns=columns,
                        row_count=row_count,
                    )
                )
            except Exception as e:
                logger.warning(f"[{db_name}] Failed to load schema for {table}: {e}")
                continue
        return responses

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def query_read(self, user: KeycloakUser, request: RawSQLRequest) -> TabularQueryResponse:
        sql = request.query.strip()
        if not sql.lower().startswith("select"):
            raise ValueError("Only SELECT statements are allowed on the read endpoint")
        store, db_name = self._require_store()
        df = store.execute_sql_query(sql)
        return TabularQueryResponse(db_name=db_name, sql_query=sql, rows=df.to_dict(orient="records"), error=None)

    @authorize(action=Action.UPDATE, resource=Resource.TABLES)
    @authorize(action=Action.CREATE, resource=Resource.TABLES)
    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    def query_write(self, user: KeycloakUser, request: RawSQLRequest) -> TabularQueryResponse:
        sql = request.query.strip()
        if not sql:
            raise ValueError("Empty SQL string provided")
        store, db_name = self._require_store()
        self._check_write_allowed(db_name)
        store.execute_update_query(sql)
        return TabularQueryResponse(db_name=db_name, sql_query=sql, rows=[], error=None)
