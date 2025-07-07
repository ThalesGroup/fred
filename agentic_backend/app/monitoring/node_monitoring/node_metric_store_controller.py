# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
node_metric_store_controller.py

Defines the FastAPI controller for NodeMetricStore routes.

Registers:
- Raw metric retrieval
- Numerical aggregation with flexible groupby and aggregation
- Categorical extraction

Routes are prefixed under /metrics/nodes
"""


from fastapi import APIRouter
import logging

from fred.monitoring.metric_controller_factory import register_metric_routes
from fred.monitoring.node_monitoring.node_metric_type import NodeMetric
from fred.monitoring.metric_types import NumericalMetric, CategoricalMetric
from fred.monitoring.node_monitoring.node_metric_store import get_node_metric_store

logger = logging.getLogger(__name__)


class NodeMetricStoreController:
    """
    FastAPI controller for NodeMetricStore.

    On initialization, automatically registers the following endpoints:
    - /metrics/nodes/all : Raw NodeMetric records within a time window.
    - /metrics/nodes/numerical : Aggregated numerical metrics with time bucketing, groupby, aggregation.
    - /metrics/nodes/categorical : Extracted categorical dimensions for filtering/analysis.
    """
    def __init__(self, router: APIRouter):
        """
        Registers metric routes to the provided FastAPI router.

        Args:
            router (APIRouter): The FastAPI router to attach endpoints to.
        """
        store = get_node_metric_store()
        register_metric_routes(
            router=router,
            store=store,
            MetricType=NodeMetric,
            NumericalType=NumericalMetric,
            CategoricalType=CategoricalMetric,
            prefix="nodes"
        )
