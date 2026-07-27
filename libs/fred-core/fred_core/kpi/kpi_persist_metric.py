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
from typing import Optional

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import Dims, KPIActor

PERSIST_METRIC_ACTOR = KPIActor(type="system", user_id=None)


def record_persist_metrics(
    kpi_writer: Optional[BaseKPIWriter],
    *,
    store: str,
    op: str,
    pool_wait_ms: float,
    sql_ms: float,
) -> None:
    """
    Emit `persist_pool_wait_ms` and `persist_sql_ms` for one checkpoint/history
    write, split into connection-acquisition time vs. actual query time.

    `store` and `op` are bounded-cardinality dims (e.g. store="checkpoint",
    op="put") — never a thread/session/user id.
    """
    if kpi_writer is None:
        return
    dims: Dims = {"store": store, "op": op}
    kpi_writer.emit(
        name="persist_pool_wait_ms",
        type="timer",
        value=pool_wait_ms,
        unit="ms",
        dims=dims,
        actor=PERSIST_METRIC_ACTOR,
    )
    kpi_writer.emit(
        name="persist_sql_ms",
        type="timer",
        value=sql_ms,
        unit="ms",
        dims=dims,
        actor=PERSIST_METRIC_ACTOR,
    )
