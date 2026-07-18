# Copyright Thales 2026
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

"""Shared factory for building a BaseLogStore from LogStorageConfig.

Why this exists:
- Every backend (control-plane, fred-agents, knowledge-flow) wants the same
  choice — OpenSearch when configured, an in-memory ring otherwise — and had
  started re-deriving it independently (knowledge-flow had it right;
  control-plane and fred-agents hardcoded NullLogStore/RamLogStore instead of
  reading storage.log_store at all). One factory, mirroring
  fred_core.kpi.kpi_factory.build_kpi_writer's shape, replaces all of them.
"""

from __future__ import annotations

from typing import Optional

from fred_core.common.resilient_sink import ResilientSinkStore
from fred_core.common.structures import OpenSearchIndexConfig, OpenSearchStoreConfig
from fred_core.logs.base_log_store import BaseLogStore
from fred_core.logs.log_structures import InMemoryLogStorageConfig, LogStorageConfig
from fred_core.logs.memory_log_store import RamLogStore
from fred_core.logs.opensearch_log_store import OpenSearchLogStore


def build_log_store(
    *,
    log_store_config: Optional[LogStorageConfig],
    opensearch_config: Optional[OpenSearchStoreConfig],
) -> BaseLogStore:
    """
    Build the BaseLogStore a service's log_setup() should use.

    - `log_store_config` is opensearch -> a durable OpenSearchLogStore, backed
      by the same `storage.opensearch` connection already used for KPI/vector
      data (see docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §6).
    - `log_store_config` is in-memory or absent -> RamLogStore, a bounded
      ring — fine for local dev/k3d, not a durability guarantee.
    - anything else (e.g. the declared-but-unimplemented "stdout" variant) is
      a configuration error, not a silent fallback — a deployment that asked
      for a specific backend should fail closed if it isn't available rather
      than quietly landing somewhere else.
    """
    if isinstance(log_store_config, OpenSearchIndexConfig):
        if opensearch_config is None:
            raise ValueError(
                "storage.log_store is 'opensearch' but storage.opensearch is not configured"
            )
        # OpenSearchStoreConfig's own validator already fails config loading
        # closed if a password is missing — no need to re-check it here.
        # ResilientSinkStore: writes are handed to a background thread via a
        # bounded queue and short-circuited on repeated failure, so a
        # slow/down OpenSearch cluster can never block or fail the business
        # request that triggered a log line (issue #2009).
        return ResilientSinkStore(  # type: ignore[return-value]
            OpenSearchLogStore(
                host=opensearch_config.host,
                index=log_store_config.index,
                username=opensearch_config.username,
                password=opensearch_config.password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
            )
        )
    if log_store_config is None or isinstance(
        log_store_config, InMemoryLogStorageConfig
    ):
        return RamLogStore(capacity=1000)
    raise ValueError(f"Unsupported log store configuration: {log_store_config!r}")


__all__ = ["build_log_store"]
