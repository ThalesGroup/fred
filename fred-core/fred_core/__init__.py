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

from fred_core.common.utils import raise_internal_error
from fred_core.security.keycloak import (
    get_current_user,
    split_realm_url,
    initialize_keycloak,
)
from fred_core.security.structure import (
    KeycloakUser,
    SecurityConfiguration,
)
from fred_core.store.vector_search import VectorSearchHit
from fred_core.common.lru_cache import ThreadSafeLRUCache
from fred_core.common.structures import (
    BaseModelWithId,
    OpenSearchStoreConfig,
    OpenSearchIndexConfig,
    DuckdbStoreConfig,
    PostgresStoreConfig,
    PostgresTableConfig,
    StoreConfig,
    LogStoreConfig,
)
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from fred_core.kpi.kpi_writer_structures import (
    KPIEvent,
    KPIActor,
    Metric,
    MetricType,
    Cost,
    Quantities,
    Trace,
)
from fred_core.kpi.kpi_reader_structures import (
    KPIQuery,
    KPIQueryResult,
    TimeBucket,
)
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.security.outbound import ClientCredentialsProvider, BearerAuth, TokenExchangeProvider
from fred_core.security.backend_to_backend_auth import (
    B2BAuthConfig,
    B2BTokenProvider,
    B2BBearerAuth,
    make_b2b_asgi_client,
)
from fred_core.kpi.log_kpi_store import KpiLogStore

__all__ = [
    "raise_internal_error",
    "get_current_user",
    "initialize_keycloak",
    "KeycloakUser",
    "SecurityConfiguration",
    "BaseModelWithId",
    "OpenSearchStoreConfig",
    "OpenSearchIndexConfig",
    "DuckdbStoreConfig",
    "PostgresStoreConfig",
    "PostgresTableConfig",
    "StoreConfig",
    "ThreadSafeLRUCache",
    "VectorSearchHit",
    "ClientCredentialsProvider",
    "BearerAuth",
    "TokenExchangeProvider",
    "OpenSearchKPIStore",
    "KPIEvent",
    "Metric",
    "MetricType",
    "Cost",
    "Quantities",
    "Trace",
    "BaseKPIStore",
    "KpiLogStore",
    "KPIQuery",
    "KPIQueryResult",
    "TimeBucket",
    "KPIWriter",
    "KPIActor",
    "LogStoreConfig",
    "B2BAuthConfig",
    "B2BTokenProvider",
    "B2BBearerAuth",
    "make_b2b_asgi_client",
    "split_realm_url",
]
