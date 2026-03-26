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
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from knowledge_flow_backend.common.structures import PrometheusConfig
from knowledge_flow_backend.features.kpi.prometheus_structures import (
    PrometheusQueryRangeRequest,
    PrometheusQueryRequest,
    PrometheusSeriesRequest,
    PrometheusTimeValue,
)

DEFAULT_DISCOVERY_WINDOW = timedelta(hours=6)
HTTPXQueryParams = tuple[tuple[str, str], ...]
METRIC_METADATA_FAMILY_SUFFIXES = ("_bucket", "_sum", "_count", "_created")
logger = logging.getLogger(__name__)


class PrometheusAPIError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]):
        super().__init__(detail.get("error", "Prometheus API error"))
        self.status_code = status_code
        self.detail = detail


class PrometheusOpsService:
    def __init__(
        self,
        config: PrometheusConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._base_url = config.base_url.rstrip("/")
        logger.info(
            "[PROM-SVC] initialized base_url=%s verify_ssl=%s timeout=%ss auth_mode=%s",
            self._base_url,
            self._config.verify_ssl,
            self._config.timeout_seconds,
            self._auth_mode(),
        )

    def _truncate(self, value: Any, limit: int = 240) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _auth_mode(self) -> str:
        if self._config.bearer_token:
            return "bearer"
        if self._config.password:
            return "basic"
        return "none"

    def _summarize_payload(self, payload: Any) -> str:
        if isinstance(payload, dict):
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
        if isinstance(payload, list):
            return f"list_count={len(payload)}"
        return self._truncate(payload, 120)

    def _summarize_params(
        self,
        items: HTTPXQueryParams | list[tuple[str, str]] | None,
    ) -> str:
        if not items:
            return "none"
        return ", ".join(f"{key}={self._truncate(value, 120)}" for key, value in items)

    async def instant_query(
        self,
        request: PrometheusQueryRequest,
    ) -> dict[str, Any]:
        logger.info(
            "[PROM-SVC] instant_query query=%s time=%s timeout=%s",
            self._truncate(request.query),
            request.time,
            request.timeout,
        )
        body = [("query", request.query)]
        if request.time is not None:
            body.append(("time", self._serialize_time_value(request.time)))
        if request.timeout is not None:
            body.append(("timeout", request.timeout))
        return await self._request("POST", "api/v1/query", data=body)

    async def range_query(
        self,
        request: PrometheusQueryRangeRequest,
    ) -> dict[str, Any]:
        logger.info(
            "[PROM-SVC] range_query query=%s start=%s end=%s step=%s timeout=%s",
            self._truncate(request.query),
            request.start,
            request.end,
            request.step,
            request.timeout,
        )
        body = [
            ("query", request.query),
            ("start", self._serialize_time_value(request.start)),
            ("end", self._serialize_time_value(request.end)),
            ("step", str(request.step)),
        ]
        if request.timeout is not None:
            body.append(("timeout", request.timeout))
        return await self._request("POST", "api/v1/query_range", data=body)

    async def series(
        self,
        request: PrometheusSeriesRequest,
    ) -> dict[str, Any]:
        start, end = self._bounded_window(request.start, request.end)
        logger.info(
            "[PROM-SVC] series matchers=%s start=%s end=%s",
            self._truncate(request.matchers),
            start,
            end,
        )
        body = [("match[]", matcher) for matcher in request.matchers]
        body.extend([("start", start), ("end", end)])
        return await self._request("POST", "api/v1/series", data=body)

    async def metadata(
        self,
        *,
        metric: str | None,
        limit: int,
    ) -> dict[str, Any]:
        metric_name = metric.strip() if isinstance(metric, str) else None
        logger.info(
            "[PROM-SVC] metadata metric=%s limit=%s",
            metric_name,
            limit,
        )
        params: list[tuple[str, str]] = [("limit", str(limit))]
        if metric_name:
            params.append(("metric", metric_name))
        payload = await self._request("GET", "api/v1/metadata", params=tuple(params))

        if not metric_name:
            return payload
        if self._extract_metadata_entries(payload, metric_name):
            return payload

        fallback_metric_name = self._metadata_family_name(metric_name)
        if fallback_metric_name is None or fallback_metric_name == metric_name:
            logger.info("[PROM-SVC] metadata empty for metric=%s without fallback", metric_name)
            return payload

        logger.info(
            "[PROM-SVC] metadata fallback requested_metric=%s fallback_metric=%s",
            metric_name,
            fallback_metric_name,
        )
        fallback_payload = await self._request(
            "GET",
            "api/v1/metadata",
            params=(("limit", str(limit)), ("metric", fallback_metric_name)),
        )
        fallback_entries = self._extract_metadata_entries(
            fallback_payload,
            fallback_metric_name,
        )
        if not fallback_entries:
            logger.info(
                "[PROM-SVC] metadata fallback empty requested_metric=%s fallback_metric=%s",
                metric_name,
                fallback_metric_name,
            )
            return payload

        merged_data = fallback_payload.get("data")
        if isinstance(merged_data, dict):
            merged_data = dict(merged_data)
            merged_data[metric_name] = fallback_entries
        else:
            merged_data = {
                fallback_metric_name: fallback_entries,
                metric_name: fallback_entries,
            }

        warnings: list[str] = []
        original_warnings = payload.get("warnings")
        if isinstance(original_warnings, list):
            warnings.extend(str(warning) for warning in original_warnings)
        fallback_warnings = fallback_payload.get("warnings")
        if isinstance(fallback_warnings, list):
            warnings.extend(str(warning) for warning in fallback_warnings)
        warnings.append(f"Metadata for {metric_name} resolved from base metric {fallback_metric_name}.")

        resolved_payload = {
            **fallback_payload,
            "data": merged_data,
            "resolvedMetric": fallback_metric_name,
        }
        if warnings:
            resolved_payload["warnings"] = warnings
        return resolved_payload

    async def labels(self) -> dict[str, Any]:
        logger.info("[PROM-SVC] labels")
        return await self._request("GET", "api/v1/labels")

    async def metrics(
        self,
        *,
        limit: int,
        search: str | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "[PROM-SVC] metrics limit=%s search=%s",
            limit,
            search,
        )
        payload = await self._request("GET", "api/v1/label/__name__/values")
        raw_metrics = payload.get("data")
        if not isinstance(raw_metrics, list):
            logger.warning(
                "[PROM-SVC] metrics unexpected payload summary=%s",
                self._summarize_payload(payload),
            )
            return payload

        filtered_metrics = [metric for metric in raw_metrics if isinstance(metric, str)]
        initial_count = len(filtered_metrics)
        if search:
            needle = search.strip().lower()
            if needle:
                filtered_metrics = [metric for metric in filtered_metrics if needle in metric.lower()]

        logger.info(
            "[PROM-SVC] metrics filtered initial_count=%s filtered_count=%s returned=%s",
            initial_count,
            len(filtered_metrics),
            min(len(filtered_metrics), limit),
        )

        return {
            **payload,
            "data": filtered_metrics[:limit],
        }

    async def metrics_catalog(
        self,
        *,
        limit: int,
        search: str | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "[PROM-SVC] metrics_catalog limit=%s search=%s",
            limit,
            search,
        )
        metrics_payload = await self.metrics(limit=limit, search=search)
        raw_metrics = metrics_payload.get("data")
        if not isinstance(raw_metrics, list):
            logger.warning(
                "[PROM-SVC] metrics_catalog unexpected metrics payload summary=%s",
                self._summarize_payload(metrics_payload),
            )
            return metrics_payload

        warnings: list[str] = []
        raw_warnings = metrics_payload.get("warnings")
        if isinstance(raw_warnings, list):
            warnings.extend(str(warning) for warning in raw_warnings)

        catalog: list[dict[str, Any]] = []
        for metric_name in raw_metrics:
            if not isinstance(metric_name, str):
                continue

            entry: dict[str, Any] = {"name": metric_name}
            logger.info("[PROM-SVC] metrics_catalog enrich metric=%s", metric_name)
            try:
                metadata_payload = await self.metadata(metric=metric_name, limit=1)
            except PrometheusAPIError as exc:
                logger.warning(
                    "[PROM-SVC] metrics_catalog metadata unavailable metric=%s error=%s",
                    metric_name,
                    exc.detail.get("error", "unknown error"),
                )
                warnings.append(f"Metadata unavailable for {metric_name}: {exc.detail.get('error', 'unknown error')}")
                catalog.append(entry)
                continue

            metadata_entries = self._extract_metadata_entries(metadata_payload, metric_name)
            if metadata_entries:
                metadata = metadata_entries[0]
                if isinstance(metadata, dict):
                    help_text = metadata.get("help")
                    metric_type = metadata.get("type")
                    metric_unit = metadata.get("unit")
                    if isinstance(help_text, str) and help_text:
                        entry["help"] = help_text
                    if isinstance(metric_type, str) and metric_type:
                        entry["type"] = metric_type
                    if isinstance(metric_unit, str) and metric_unit:
                        entry["unit"] = metric_unit

            metadata_warnings = metadata_payload.get("warnings")
            if isinstance(metadata_warnings, list):
                warnings.extend(str(warning) for warning in metadata_warnings)

            catalog.append(entry)

        response: dict[str, Any] = {
            "status": metrics_payload.get("status", "success"),
            "data": catalog,
        }
        if warnings:
            response["warnings"] = warnings
        logger.info(
            "[PROM-SVC] metrics_catalog complete entries=%s warnings=%s",
            len(catalog),
            len(warnings),
        )
        return response

    async def label_values(
        self,
        label_name: str,
        *,
        start: str | None,
        end: str | None,
        matchers: list[str] | None,
    ) -> dict[str, Any]:
        start_value, end_value = self._bounded_window(start, end)
        logger.info(
            "[PROM-SVC] label_values label=%s start=%s end=%s matchers=%s",
            label_name,
            start_value,
            end_value,
            self._truncate(matchers),
        )
        params: list[tuple[str, str]] = [("start", start_value), ("end", end_value)]
        for matcher in matchers or []:
            params.append(("match[]", matcher))
        return await self._request(
            "GET",
            f"api/v1/label/{label_name}/values",
            params=tuple(params),
        )

    async def targets(self) -> dict[str, Any]:
        logger.info("[PROM-SVC] targets")
        return await self._request("GET", "api/v1/targets")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: HTTPXQueryParams | None = None,
        data: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        headers = self._build_headers()
        auth = self._build_auth()
        content: bytes | None = None
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            content = urlencode(data).encode()

        start_time = perf_counter()
        logger.info(
            "[PROM-SVC] upstream_request method=%s path=%s auth_mode=%s params=%s data=%s",
            method,
            path,
            self._auth_mode(),
            self._summarize_params(params),
            self._summarize_params(data),
        )
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                verify=self._config.verify_ssl,
                timeout=self._config.timeout_seconds,
                transport=self._transport,
                auth=auth,
            ) as client:
                response = await client.request(
                    method,
                    path.lstrip("/"),
                    params=params,
                    content=content,
                )
        except httpx.TimeoutException as exc:
            logger.warning(
                "[PROM-SVC] upstream timeout method=%s path=%s elapsed_ms=%.1f",
                method,
                path,
                (perf_counter() - start_time) * 1000,
            )
            raise PrometheusAPIError(
                504,
                {
                    "status": "error",
                    "errorType": "timeout",
                    "error": "Timed out while querying Prometheus.",
                },
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "[PROM-SVC] upstream transport error method=%s path=%s elapsed_ms=%.1f error=%s",
                method,
                path,
                (perf_counter() - start_time) * 1000,
                exc,
            )
            raise PrometheusAPIError(
                502,
                {
                    "status": "error",
                    "errorType": "transport",
                    "error": f"Prometheus transport error: {exc}",
                },
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning(
                "[PROM-SVC] upstream invalid json method=%s path=%s status=%s elapsed_ms=%.1f",
                method,
                path,
                response.status_code,
                (perf_counter() - start_time) * 1000,
            )
            raise PrometheusAPIError(
                502,
                {
                    "status": "error",
                    "errorType": "invalid_response",
                    "error": "Prometheus returned a non-JSON response.",
                },
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "[PROM-SVC] upstream unexpected payload type method=%s path=%s status=%s type=%s elapsed_ms=%.1f",
                method,
                path,
                response.status_code,
                type(payload).__name__,
                (perf_counter() - start_time) * 1000,
            )
            raise PrometheusAPIError(
                502,
                {
                    "status": "error",
                    "errorType": "invalid_response",
                    "error": "Prometheus returned an unexpected payload.",
                },
            )

        if response.is_success:
            logger.info(
                "[PROM-SVC] upstream_response method=%s path=%s status=%s elapsed_ms=%.1f summary=%s",
                method,
                path,
                response.status_code,
                (perf_counter() - start_time) * 1000,
                self._summarize_payload(payload),
            )
            return payload

        payload.setdefault("status", "error")
        payload.setdefault("errorType", "upstream_http")
        payload.setdefault(
            "error",
            f"Prometheus request failed with status {response.status_code}.",
        )
        logger.warning(
            "[PROM-SVC] upstream_http_error method=%s path=%s status=%s elapsed_ms=%.1f summary=%s",
            method,
            path,
            response.status_code,
            (perf_counter() - start_time) * 1000,
            self._summarize_payload(payload),
        )
        raise PrometheusAPIError(response.status_code, payload)

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._config.bearer_token:
            headers["Authorization"] = f"Bearer {self._config.bearer_token}"
        return headers

    def _build_auth(self) -> httpx.BasicAuth | None:
        if self._config.bearer_token:
            return None
        if self._config.password:
            return httpx.BasicAuth(self._config.username or "admin", self._config.password)
        return None

    def _extract_metadata_entries(
        self,
        payload: dict[str, Any],
        metric_name: str,
    ) -> list[dict[str, Any]]:
        raw_data = payload.get("data")
        if not isinstance(raw_data, dict):
            return []
        raw_entries = raw_data.get(metric_name)
        if not isinstance(raw_entries, list):
            return []

        return [entry for entry in raw_entries if isinstance(entry, dict)]

    def _metadata_family_name(self, metric_name: str) -> str | None:
        for suffix in METRIC_METADATA_FAMILY_SUFFIXES:
            if metric_name.endswith(suffix):
                base_name = metric_name.removesuffix(suffix)
                if base_name:
                    return base_name
        return None

    def _bounded_window(
        self,
        start: PrometheusTimeValue | None,
        end: PrometheusTimeValue | None,
    ) -> tuple[str, str]:
        now = self._normalize_datetime(self._now_provider())

        if start is not None and end is not None:
            start_value, end_value = (
                self._serialize_time_value(start),
                self._serialize_time_value(end),
            )
            logger.info(
                "[PROM-SVC] bounded_window explicit start=%s end=%s",
                start_value,
                end_value,
            )
            return start_value, end_value

        if start is not None:
            start_value = self._serialize_time_value(start)
            end_value = self._format_datetime(now)
            logger.info(
                "[PROM-SVC] bounded_window start_only start=%s end=%s",
                start_value,
                end_value,
            )
            return start_value, end_value

        if end is not None:
            end_dt = self._parse_datetime(end) or now
            start_value, end_value = (
                self._format_datetime(end_dt - DEFAULT_DISCOVERY_WINDOW),
                self._serialize_time_value(end),
            )
            logger.info(
                "[PROM-SVC] bounded_window end_only start=%s end=%s",
                start_value,
                end_value,
            )
            return start_value, end_value

        start_value, end_value = (
            self._format_datetime(now - DEFAULT_DISCOVERY_WINDOW),
            self._format_datetime(now),
        )
        logger.info(
            "[PROM-SVC] bounded_window default start=%s end=%s",
            start_value,
            end_value,
        )
        return start_value, end_value

    def _serialize_time_value(self, value: PrometheusTimeValue) -> str:
        if isinstance(value, datetime):
            return self._format_datetime(value)
        return str(value)

    def _parse_datetime(self, value: PrometheusTimeValue) -> datetime | None:
        if isinstance(value, datetime):
            return self._normalize_datetime(value)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if not isinstance(value, str):
            return None

        normalized = value.strip()
        if not normalized:
            return None
        try:
            return datetime.fromtimestamp(float(normalized), tz=timezone.utc)
        except ValueError:
            pass
        try:
            return self._normalize_datetime(datetime.fromisoformat(normalized.replace("Z", "+00:00")))
        except ValueError:
            return None

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _format_datetime(self, value: datetime) -> str:
        return self._normalize_datetime(value).isoformat().replace("+00:00", "Z")
