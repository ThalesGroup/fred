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
        integrations = get_app_context().configuration.integrations
        config = integrations.prometheus if integrations is not None else None
        if config is None:
            raise ValueError("Prometheus MCP is enabled but no integrations.prometheus configuration is defined.")
        self.service = PrometheusOpsService(config)
        self._register_routes(router)

    def _truncate(self, value: Any, limit: int = 240) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _user_ref(self, user: KeycloakUser) -> str:
        return str(getattr(user, "preferred_username", None) or getattr(user, "email", None) or getattr(user, "sub", None) or "unknown")

    def _summarize_response(self, payload: dict[str, Any]) -> str:
        status = payload.get("status", "unknown")
        data = payload.get("data")
        parts = [f"status={status}"]
        if isinstance(data, list):
            parts.append(f"data_count={len(data)}")
        elif isinstance(data, dict):
            result_type = data.get("resultType")
            if isinstance(result_type, str):
                parts.append(f"result_type={result_type}")
            result = data.get("result")
            if isinstance(result, list):
                parts.append(f"result_count={len(result)}")
            active_targets = data.get("activeTargets")
            if isinstance(active_targets, list):
                parts.append(f"active_targets={len(active_targets)}")
        warnings = payload.get("warnings")
        if isinstance(warnings, list) and warnings:
            parts.append(f"warnings={len(warnings)}")
        return " ".join(parts)

    def _log_request(
        self,
        endpoint: str,
        user: KeycloakUser,
        **details: Any,
    ) -> None:
        rendered = ", ".join(f"{key}={self._truncate(value, 120)}" for key, value in details.items()) or "no_args"
        logger.info(
            "[PROM-CTRL] request endpoint=%s user=%s %s",
            endpoint,
            self._user_ref(user),
            rendered,
        )

    def _log_success(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> None:
        logger.info(
            "[PROM-CTRL] success endpoint=%s %s",
            endpoint,
            self._summarize_response(payload),
        )

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
                self._log_request(
                    "prometheus_query",
                    user,
                    query=body.query,
                    time=body.time,
                    timeout=body.timeout,
                )
                payload = await self.service.instant_query(body)
                self._log_success("prometheus_query", payload)
                return payload
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
                self._log_request(
                    "prometheus_query_range",
                    user,
                    query=body.query,
                    start=body.start,
                    end=body.end,
                    step=body.step,
                    timeout=body.timeout,
                )
                payload = await self.service.range_query(body)
                self._log_success("prometheus_query_range", payload)
                return payload
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
                self._log_request(
                    "prometheus_series",
                    user,
                    matchers=body.matchers,
                    start=body.start,
                    end=body.end,
                )
                payload = await self.service.series(body)
                self._log_success("prometheus_series", payload)
                return payload
            except Exception as exc:
                raise self._handle_error(exc)

        @router.get(
            "/prometheus/metrics",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_metrics",
            summary="List available Prometheus metric names",
        )
        async def metrics(
            limit: int = Query(
                500,
                ge=1,
                le=5000,
                description="Maximum number of metric names to return.",
            ),
            search: str | None = Query(
                None,
                description="Optional case-insensitive substring filter applied to metric names.",
            ),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                self._log_request(
                    "prometheus_metrics",
                    user,
                    limit=limit,
                    search=search,
                )
                payload = await self.service.metrics(limit=limit, search=search)
                self._log_success("prometheus_metrics", payload)
                return payload
            except Exception as exc:
                raise self._handle_error(exc)

        @router.get(
            "/prometheus/metrics_catalog",
            tags=["Prometheus"],
            response_model=dict[str, Any],
            operation_id="prometheus_metrics_catalog",
            summary="List metric names with compact metadata",
        )
        async def metrics_catalog(
            limit: int = Query(
                50,
                ge=1,
                le=200,
                description="Maximum number of catalog entries to return.",
            ),
            search: str | None = Query(
                None,
                description="Optional case-insensitive substring filter applied to metric names.",
            ),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.METRICS)
            try:
                self._log_request(
                    "prometheus_metrics_catalog",
                    user,
                    limit=limit,
                    search=search,
                )
                payload = await self.service.metrics_catalog(limit=limit, search=search)
                self._log_success("prometheus_metrics_catalog", payload)
                return payload
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
                self._log_request(
                    "prometheus_metadata",
                    user,
                    metric=metric,
                    limit=limit,
                )
                payload = await self.service.metadata(metric=metric, limit=limit)
                self._log_success("prometheus_metadata", payload)
                return payload
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
                self._log_request("prometheus_labels", user)
                payload = await self.service.labels()
                self._log_success("prometheus_labels", payload)
                return payload
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
                self._log_request(
                    "prometheus_label_values",
                    user,
                    label_name=label_name,
                    start=start,
                    end=end,
                    matchers=matchers,
                )
                payload = await self.service.label_values(
                    label_name,
                    start=start,
                    end=end,
                    matchers=matchers,
                )
                self._log_success("prometheus_label_values", payload)
                return payload
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
                self._log_request("prometheus_targets", user)
                payload = await self.service.targets()
                self._log_success("prometheus_targets", payload)
                return payload
            except Exception as exc:
                raise self._handle_error(exc)

    def _handle_error(self, exc: Exception) -> HTTPException:
        logger.error("[PROM] error: %s", exc, exc_info=True)
        if isinstance(exc, PrometheusAPIError):
            return HTTPException(status_code=exc.status_code, detail=exc.detail)
        return HTTPException(status_code=500, detail=str(exc))
