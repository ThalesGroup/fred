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

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import Annotated, List, Tuple
import logging

from fred.monitoring.metric_store import MetricStore, Precision, Aggregation
from fred.monitoring.inmemory_metric_store import get_metric_store
from fred.monitoring.metric_types import CategoricalMetric, MetaData, NumericalMetric

logger = logging.getLogger(__name__)


def parse_dates(start: str, end: str) -> Tuple[datetime, datetime]:
    try:
        return datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dates. Use ISO 8601 format.")


class MetricStoreController:
    def __init__(self, router: APIRouter):
        self.metric_store: MetricStore = get_metric_store()

        @router.get("/metrics/all", response_model=List[MetaData], tags=["Metrics"])
        def get_all_metrics(
            start: Annotated[str, Query(description="Start date in ISO 8601 format")],
            end: Annotated[str, Query(description="End date in ISO 8601 format")]
        ) -> List[MetaData]:
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_by_date_range(start_dt, end_dt)

        @router.get("/metrics/numerical", response_model=List[NumericalMetric], tags=["Metrics"])
        def get_numerical_metrics(
            start: Annotated[str, Query()],
            end: Annotated[str, Query()],
            precision: Precision = Precision.hour,
            agg: Aggregation = Aggregation.avg,
        ) -> List[NumericalMetric]:
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_numerical_aggregated_by_precision(
                start=start_dt, end=end_dt, precision=precision, agg=agg
            )

        @router.get("/metrics/categorical", response_model=List[CategoricalMetric], tags=["Metrics"])
        def get_categorical_metrics(
            start: Annotated[str, Query()],
            end: Annotated[str, Query()]
        ) -> List[CategoricalMetric]:
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_categorical_rows_by_date_range(
                start=start_dt, end=end_dt
            )
