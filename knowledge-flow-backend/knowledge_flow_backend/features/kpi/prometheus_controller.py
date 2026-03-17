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

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user

from knowledge_flow_backend.application_context import get_app_context
from knowledge_flow_backend.features.kpi.prometheus_service import (
    PrometheusAPIError,
    PrometheusOpsService,
)
from knowledge_flow_backend.features.kpi.prometheus_structures import (
    PrometheusQueryRangeRequest,
    PrometheusQueryRequest,
    PrometheusSeriesRequest,
)

logger = logging.getLogger(__name__)


class PrometheusOpsController:
    """Read-only Prometheus HTTP API endpoints for monitoring agents."""

    def __init__(self, router: APIRouter):
        config = get_app_context().configuration.prometheus
        if config is None:
            raise ValueError(
                "Prometheus MCP is enabled but no Prometheus configuration is defined."
            )
        self.service = PrometheusOpsService(config)
        self._register_routes(router)

    def _register_routes(self, router: APIRouter) -> None:
        @router.post(
            "/prometheus/query",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_query",
            summary="Run an instant PromQL query",
        )
        async def query(
            body: PrometheusQueryRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                return await self.service.instant_query(body)
            except Exception as exc:
                raise self._handle_error(exc)

        @router.post(
            "/prometheus/query_range",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_query_range",
            summary="Run a ranged PromQL query",
        )
        async def query_range(
            body: PrometheusQueryRangeRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                return await self.service.range_query(body)
            except Exception as exc:
                raise self._handle_error(exc)

        @router.post(
            "/prometheus/series",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_series",
            summary="Discover metric series with bounded time filters",
        )
        async def series(
            body: PrometheusSeriesRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                return await self.service.series(body)
            except Exception as exc:
                raise self._handle_error(exc)

        @router.get(
            "/prometheus/metadata",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_metadata",
            summary="List Prometheus metric metadata",
        )
        async def metadata(
            metric: str | None = Query(
                None,
                description="Optional metric name filter.",
            ),
            limit: int = Query(
                200,
                ge=1,
                le=1000,
                description="Maximum number of metadata entries returned by Prometheus.",
            ),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                return await self.service.metadata(metric=metric, limit=limit)
            except Exception as exc:
                raise self._handle_error(exc)

        @router.get(
            "/prometheus/labels",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_labels",
            summary="List label names known to Prometheus",
        )
        async def labels(user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                return await self.service.labels()
            except Exception as exc:
                raise self._handle_error(exc)

        @router.get(
            "/prometheus/labels/{label_name}/values",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_label_values",
            summary="List label values, optionally narrowed by matcher and time window",
        )
        async def label_values(
            label_name: str = Path(..., description="Prometheus label name."),
            start: str | None = Query(
                None,
                description="Optional range start; defaults to a bounded discovery window.",
            ),
            end: str | None = Query(
                None,
                description="Optional range end; defaults to a bounded discovery window.",
            ),
            matchers: list[str] | None = Query(
                None,
                alias="match[]",
                description="Optional series matchers used to scope label values.",
            ),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                return await self.service.label_values(
                    label_name,
                    start=start,
                    end=end,
                    matchers=matchers,
                )
            except Exception as exc:
                raise self._handle_error(exc)

        @router.get(
            "/prometheus/targets",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_targets",
            summary="Inspect Prometheus scrape targets",
        )
        async def targets(user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                return await self.service.targets()
            except Exception as exc:
                raise self._handle_error(exc)

    def _handle_error(self, exc: Exception) -> HTTPException:
        logger.error("[PROM] error: %s", exc, exc_info=True)
        if isinstance(exc, PrometheusAPIError):
            return HTTPException(status_code=exc.status_code, detail=exc.detail)
        return HTTPException(status_code=500, detail=str(exc))
