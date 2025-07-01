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
tool_metric_store_controller.py

Defines the FastAPI controller for ToolMetricStore routes.

Registers:
- Raw metric retrieval.
- Numerical aggregation with groupby and aggregation functions.
- Categorical extraction for analytics.

Routes are automatically mounted under /metrics/tools.
"""

from fastapi import APIRouter
import logging

from fred.monitoring.metric_controller_factory import register_metric_routes
from fred.monitoring.tool_monitoring.tool_metric_type import ToolMetric
from fred.monitoring.metric_types import NumericalMetric, CategoricalMetric
from fred.monitoring.tool_monitoring.tool_metric_store import get_tool_metric_store

logger = logging.getLogger(__name__)


class ToolMetricStoreController:
    """
    FastAPI controller for ToolMetricStore.

    On initialization:
    - Registers REST endpoints for metrics retrieval.
    - Supports raw, aggregated numerical, and categorical metrics.

    Endpoints prefix:
        /metrics/tools
    """
    def __init__(self, router: APIRouter):
        """
        Registers metric routes to the provided FastAPI router.

        Args:
            router (APIRouter): The FastAPI router to attach endpoints to.
        """
        store = get_tool_metric_store()
        register_metric_routes(
            router=router,
            store=store,
            MetricType=ToolMetric,
            NumericalType=NumericalMetric,
            CategoricalType=CategoricalMetric,
            prefix="tools"
        )