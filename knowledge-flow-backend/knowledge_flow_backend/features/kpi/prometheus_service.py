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

from datetime import datetime, timedelta, timezone
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

    async def instant_query(
        self,
        request: PrometheusQueryRequest,
    ) -> dict[str, Any]:
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
        body = [("match[]", matcher) for matcher in request.matchers]
        body.extend([("start", start), ("end", end)])
        return await self._request("POST", "api/v1/series", data=body)

    async def metadata(
        self,
        *,
        metric: str | None,
        limit: int,
    ) -> dict[str, Any]:
        params: list[tuple[str, str]] = [("limit", str(limit))]
        if metric:
            params.append(("metric", metric.strip()))
        return await self._request("GET", "api/v1/metadata", params=params)

    async def labels(self) -> dict[str, Any]:
        return await self._request("GET", "api/v1/labels")

    async def label_values(
        self,
        label_name: str,
        *,
        start: str | None,
        end: str | None,
        matchers: list[str] | None,
    ) -> dict[str, Any]:
        start_value, end_value = self._bounded_window(start, end)
        params: list[tuple[str, str]] = [("start", start_value), ("end", end_value)]
        for matcher in matchers or []:
            params.append(("match[]", matcher))
        return await self._request(
            "GET",
            f"api/v1/label/{label_name}/values",
            params=params,
        )

    async def targets(self) -> dict[str, Any]:
        return await self._request("GET", "api/v1/targets")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str]] | None = None,
        data: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self._config.bearer_token:
            headers["Authorization"] = f"Bearer {self._config.bearer_token}"
        content: bytes | None = None
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            content = urlencode(data).encode()

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                verify=self._config.verify_ssl,
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    path.lstrip("/"),
                    params=params,
                    content=content,
                )
        except httpx.TimeoutException as exc:
            raise PrometheusAPIError(
                504,
                {
                    "status": "error",
                    "errorType": "timeout",
                    "error": "Timed out while querying Prometheus.",
                },
            ) from exc
        except httpx.HTTPError as exc:
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
            raise PrometheusAPIError(
                502,
                {
                    "status": "error",
                    "errorType": "invalid_response",
                    "error": "Prometheus returned a non-JSON response.",
                },
            ) from exc

        if not isinstance(payload, dict):
            raise PrometheusAPIError(
                502,
                {
                    "status": "error",
                    "errorType": "invalid_response",
                    "error": "Prometheus returned an unexpected payload.",
                },
            )

        if response.is_success:
            return payload

        payload.setdefault("status", "error")
        payload.setdefault("errorType", "upstream_http")
        payload.setdefault(
            "error",
            f"Prometheus request failed with status {response.status_code}.",
        )
        raise PrometheusAPIError(response.status_code, payload)

    def _bounded_window(
        self,
        start: PrometheusTimeValue | None,
        end: PrometheusTimeValue | None,
    ) -> tuple[str, str]:
        now = self._normalize_datetime(self._now_provider())

        if start is not None and end is not None:
            return (
                self._serialize_time_value(start),
                self._serialize_time_value(end),
            )

        if start is not None:
            return self._serialize_time_value(start), self._format_datetime(now)

        if end is not None:
            end_dt = self._parse_datetime(end) or now
            return (
                self._format_datetime(end_dt - DEFAULT_DISCOVERY_WINDOW),
                self._serialize_time_value(end),
            )

        return (
            self._format_datetime(now - DEFAULT_DISCOVERY_WINDOW),
            self._format_datetime(now),
        )

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
            return self._normalize_datetime(
                datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            )
        except ValueError:
            return None

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _format_datetime(self, value: datetime) -> str:
        return self._normalize_datetime(value).isoformat().replace("+00:00", "Z")
