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

"""The frontend can read KPI analytics only through the OpenSearch KPI store."""

import pytest
from control_plane_backend.app.context import ApplicationContext
from fred_core.common.resilient_sink import ResilientSinkStore
from fred_core.common.structures import (
    KpiLogSinkConfig,
    KpiObservabilityConfig,
    KpiOpenSearchSinkConfig,
    KpiPrometheusSinkConfig,
    OpenSearchStoreConfig,
)
from fred_core.kpi.kpi_factory import build_kpi_writer
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore


@pytest.mark.parametrize(
    "log_enabled,prometheus_enabled,opensearch_enabled",
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, False),
        (False, False, True),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ],
    ids=[
        "none",
        "log",
        "prometheus",
        "log-and-prometheus",
        "opensearch",
        "log-and-opensearch",
        "prometheus-and-opensearch",
        "all",
    ],
)
def test_kpi_analytics_requires_opensearch_store(
    monkeypatch: pytest.MonkeyPatch,
    log_enabled: bool,
    prometheus_enabled: bool,
    opensearch_enabled: bool,
) -> None:
    monkeypatch.setattr(OpenSearchKPIStore, "ensure_ready", lambda self: None)
    monkeypatch.setattr(
        ResilientSinkStore,
        "__init__",
        lambda self, wrapped: setattr(self, "_wrapped", wrapped),
    )
    writer = build_kpi_writer(
        kpi_config=KpiObservabilityConfig(
            log=KpiLogSinkConfig(enabled=log_enabled),
            prometheus=KpiPrometheusSinkConfig(enabled=prometheus_enabled),
            opensearch=KpiOpenSearchSinkConfig(enabled=opensearch_enabled),
        ),
        opensearch_config=OpenSearchStoreConfig(
            host="http://localhost:9200",
            username="test",
            password="test",  # pragma: allowlist secret
        ),
        service_name="control-plane",
    )
    context = object.__new__(ApplicationContext)
    context._kpi_writer = writer

    assert (context.get_kpi_store() is not None) is opensearch_enabled


def test_kpi_analytics_requires_configured_opensearch_storage() -> None:
    writer = build_kpi_writer(
        kpi_config=KpiObservabilityConfig(
            log=KpiLogSinkConfig(enabled=False),
            prometheus=KpiPrometheusSinkConfig(enabled=False),
            opensearch=KpiOpenSearchSinkConfig(enabled=True),
        ),
        opensearch_config=None,
        service_name="control-plane",
    )
    context = object.__new__(ApplicationContext)
    context._kpi_writer = writer

    assert context.get_kpi_store() is None
