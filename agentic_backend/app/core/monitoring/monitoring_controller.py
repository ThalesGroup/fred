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


import logging
from enum import Enum
from typing import Dict, List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from fred_core import KeycloakUser, get_current_user

from app.core.chatbot.metric_structures import MetricsResponse
from app.core.monitoring.monitoring_service import AppMonitoringMetricsService

logger = logging.getLogger(__name__)


def _split_csv(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values or []:
        out.extend([p.strip() for p in v.split(",") if p and p.strip()])
    return out


class MonitoringController:
    def __init__(
        self,
        app: APIRouter,
    ):
        fastapi_tags: list[str | Enum] = ["Monitoring"]
        self.service = AppMonitoringMetricsService()

        @app.get("/healthz")
        async def healthz():
            return {"status": "ok"}

        @app.get("/ready")
        def ready():
            return {"status": "ready"}

        @app.get(
            "/metrics/chatbot/numerical",
            summary="Get aggregated numerical chatbot metrics",
            tags=fastapi_tags,
            response_model=MetricsResponse,
        )
        def get_node_numerical_metrics(
            start: str,
            end: str,
            precision: str = "hour",
            agg: List[str] = Query(default=[]),
            groupby: List[str] = Query(default=[]),
            user: KeycloakUser = Depends(get_current_user),
        ) -> MetricsResponse:
            agg = _split_csv(agg)  # supports ?agg=a:b&agg=c:d OR ?agg=a:b,c:d
            groupby = _split_csv(groupby)
            SUPPORTED_OPS = {"mean", "sum", "min", "max", "values"}
            agg_mapping: Dict[str, List[str]] = {}
            for item in agg:
                if ":" not in item:
                    raise HTTPException(
                        400, detail=f"Invalid agg parameter format: {item}"
                    )
                field, op = item.split(":")
                if op not in SUPPORTED_OPS:
                    raise HTTPException(400, detail=f"Unsupported aggregation op: {op}")
                agg_mapping.setdefault(field, []).append(op)
            return self.service.get_node_numerical_metrics(
                start=start,
                end=end,
                precision=precision,
                groupby=groupby,
                agg_mapping=agg_mapping,
                user_id=user.uid,
            )
