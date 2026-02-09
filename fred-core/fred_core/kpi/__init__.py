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

from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_phase_metric import phase_timer, record_phase_metric
from fred_core.kpi.kpi_process import emit_process_kpis
from fred_core.kpi.kpi_reader_structures import (
    FilterTerm,
    KPIQuery,
    KPIQueryResult,
    TimeBucket,
)
from fred_core.kpi.kpi_writer import KPIDefaults, KPIWriter
from fred_core.kpi.kpi_writer_structures import (
    Cost,
    KPIActor,
    KPIEvent,
    Metric,
    MetricType,
    Quantities,
    Trace,
)
from fred_core.kpi.log_kpi_store import KpiLogStore
from fred_core.kpi.noop_kpi_writer import Dims, NoOpKPIWriter
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore

__all__ = [
    "BaseKPIStore",
    "BaseKPIWriter",
    "Dims",
    "KPIWriter",
    "KPIDefaults",
    "NoOpKPIWriter",
    "KPIActor",
    "KPIEvent",
    "Metric",
    "MetricType",
    "Cost",
    "Quantities",
    "Trace",
    "FilterTerm",
    "KPIQuery",
    "KPIQueryResult",
    "TimeBucket",
    "KpiLogStore",
    "OpenSearchKPIStore",
    "PrometheusKPIStore",
    "emit_process_kpis",
    "record_phase_metric",
    "phase_timer",
]
