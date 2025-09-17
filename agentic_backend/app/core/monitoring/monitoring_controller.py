# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fred_core import KeycloakUser, get_current_user

from app.core.chatbot.metric_structures import MetricsResponse
from app.core.monitoring.monitoring_service import AppMonitoringMetricsService

logger = logging.getLogger(__name__)


class MonitoringController:
    """
    Expose monitoring endpoints (system + chatbot metrics) with an internal APIRouter.
    Can be included in the main router as: router.include_router(monitoring_controller.router)
    """

    def __init__(self, base_path: str = ""):
        self.base_path = base_path
        self.router = APIRouter(tags=["Monitoring"])
        self._register_routes()

    # ---------------------------------------------------------------------
    # Internal helper methods
    # ---------------------------------------------------------------------
    @staticmethod
    def _split_csv(values: list[str]) -> list[str]:
        out: list[str] = []
        for v in values or []:
            out.extend([p.strip() for p in v.split(",") if p and p.strip()])
        return out

    @staticmethod
    def _get_monitoring_service() -> AppMonitoringMetricsService:
        return AppMonitoringMetricsService()

    # ---------------------------------------------------------------------
    # Register all routes
    # ---------------------------------------------------------------------
    def _register_routes(self):
        @self.router.get(f"{self.base_path}/healthz", summary="Liveness check for Kubernetes", tags=["Monitoring"])
        async def healthz():
            return {"status": "ok"}

        @self.router.get(f"{self.base_path}/ready", summary="Readiness check for Kubernetes", tags=["Monitoring"])
        def ready():
            return {"status": "ready"}

        @self.router.get(
            f"{self.base_path}/metrics/system",
            summary="Expose system metrics for Prometheus scraping",
            include_in_schema=False,
        )
        def metrics():
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )

        @self.router.get(
            f"{self.base_path}/metrics/chatbot/numerical",
            summary="Get aggregated numerical chatbot metrics",
            response_model=MetricsResponse,
        )
        def get_node_numerical_metrics(
            start: str,
            end: str,
            precision: str = "hour",
            agg: List[str] = Query(default=[]),
            groupby: List[str] = Query(default=[]),
            user: KeycloakUser = Depends(get_current_user),
            service: AppMonitoringMetricsService = Depends(self._get_monitoring_service),
        ) -> MetricsResponse:
            agg = self._split_csv(agg)
            groupby = self._split_csv(groupby)
            SUPPORTED_OPS = {"mean", "sum", "min", "max", "values"}
            agg_mapping: Dict[str, List[str]] = {}
            for item in agg:
                if ":" not in item:
                    raise HTTPException(400, detail=f"Invalid agg parameter format: {item}")
                field, op = item.split(":")
                if op not in SUPPORTED_OPS:
                    raise HTTPException(400, detail=f"Unsupported aggregation op: {op}")
                agg_mapping.setdefault(field, []).append(op)
            return service.get_node_numerical_metrics(
                user,
                start=start,
                end=end,
                precision=precision,
                groupby=groupby,
                agg_mapping=agg_mapping,
                user_id=user.uid,
            )
