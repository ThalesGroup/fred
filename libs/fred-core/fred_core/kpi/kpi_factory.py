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

"""Shared factory for building a KPIWriter from KpiObservabilityConfig."""

from __future__ import annotations

import logging
from typing import Optional

from fred_core.common.structures import KpiObservabilityConfig, OpenSearchStoreConfig
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer import KPIDefaults, KPIWriter
from fred_core.kpi.log_kpi_store import KpiLogStore
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore

logger = logging.getLogger(__name__)


def build_kpi_writer(
    *,
    kpi_config: KpiObservabilityConfig,
    opensearch_config: Optional[OpenSearchStoreConfig],
    service_name: str,
    log_level: str = "info",
) -> BaseKPIWriter:
    """
    Build a KPIWriter from KpiObservabilityConfig.

    Sink stacking rules:
    - opensearch sink (if enabled): base store — writes structured KPI events to OpenSearch
    - log sink (if enabled, and no opensearch): fallback base store — structured log lines
    - prometheus sink (if enabled): wraps whatever base store was chosen as a decorator,
      so metrics are registered in the Prometheus registry AND forwarded to the base store
    - if no sink is enabled at all: returns NoOpKPIWriter

    Note: starting the Prometheus HTTP scrape endpoint (start_http_server) is the
    caller's responsibility — this factory only assembles the store stack.
    """
    log_cfg = kpi_config.log
    prom_cfg = kpi_config.prometheus
    os_cfg = kpi_config.opensearch

    # Choose base store
    base_store: Optional[BaseKPIStore] = None

    if os_cfg.enabled:
        if opensearch_config is None:
            logger.warning(
                "[KPI] opensearch sink is enabled but no storage.opensearch config found "
                "— falling back to log sink"
            )
        else:
            base_store = OpenSearchKPIStore(
                host=opensearch_config.host,
                username=opensearch_config.username,
                password=opensearch_config.password,
                secure=opensearch_config.secure,
                verify_certs=opensearch_config.verify_certs,
                index=os_cfg.index,
            )

    if base_store is None and log_cfg.enabled:
        base_store = KpiLogStore(level=log_cfg.level or log_level)

    if base_store is None and not prom_cfg.enabled:
        return NoOpKPIWriter()

    if base_store is None:
        # prometheus-only: need a no-op base to satisfy PrometheusKPIStore delegate type
        base_store = KpiLogStore(level="warning")

    store: BaseKPIStore = base_store
    if prom_cfg.enabled:
        store = PrometheusKPIStore(delegate=store)  # type: ignore[arg-type]

    return KPIWriter(
        store=store,
        defaults=KPIDefaults(static_dims={"service": service_name}),
        summary_interval_s=log_cfg.summary_interval_sec if log_cfg.enabled else None,
        summary_top_n=log_cfg.summary_top_n if log_cfg.enabled else None,
    )
