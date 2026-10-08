# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Pod-lifetime internal engine and per-user adapter for the web research SDK port."""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4

import httpx
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.web_research import (
    DailyQuota,
    WebResearchDeploymentConfig,
    WebResearchError,
    WebResearchPort,
    WebResearchRequest,
    WebResearchResult,
)
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

from fred_runtime.app.web_research_activity import (
    WebResearchActivityStore,
    activity_url,
)
from fred_runtime.runtime_context import get_runtime_context_or_none

logger = logging.getLogger(__name__)
REQUESTS = Counter(
    "fred_web_research_requests_total",
    "Web research calls",
    ["service", "operation", "outcome"],
)
DURATION = Histogram(
    "fred_web_research_duration_seconds",
    "Web research latency",
    ["service", "operation"],
)
ACTIVITY_FAILURES = Counter(
    "fred_web_research_activity_failures_total",
    "Restricted activity sink errors",
    ["service", "stage"],
)


class WebResearchService:
    def __init__(
        self,
        config: WebResearchDeploymentConfig,
        engine: AsyncEngine,
        *,
        client: httpx.AsyncClient | None = None,
        service_name: str = "fred",
    ) -> None:
        if not config.enabled:
            raise RuntimeError("Web research is disabled.")
        if engine.echo:
            raise RuntimeError(
                "Web research activity requires SQL statement logging to be disabled."
            )
        from fred_runtime.app.web_research_engine import create_engine

        self.config = config
        self.service_name = service_name
        self.store = WebResearchActivityStore(engine, config.activity_retention_days)
        self.research = create_engine(config, client)
        self._slots = asyncio.Semaphore(config.max_concurrency)

    def bind(self, binding: BoundRuntimeContext) -> WebResearchPort:
        return WebResearchAdapter(self, binding)

    async def quota(self, user_id: str, operation: str) -> DailyQuota | None:
        limit = (
            self.config.max_searches_per_user_per_day
            if operation == "web_search"
            else self.config.max_fetches_per_user_per_day
        )
        if limit is None:
            return None
        # The request's own activity row already exists, so concurrent calls never overshoot.
        used = await self.store.count_today(user_id, operation)
        if used > limit:
            raise WebResearchError("quota_exceeded")
        return DailyQuota(limit=limit, remaining=limit - used)

    async def close(self) -> None:
        await self.research.client.aclose()
        if self.research.pending:
            await asyncio.gather(*self.research.pending, return_exceptions=True)


class WebResearchAdapter(WebResearchPort):
    def __init__(
        self, service: WebResearchService, binding: BoundRuntimeContext
    ) -> None:
        self._service = service
        self._binding = binding

    async def check_ready(self) -> None:
        try:
            await self._service.store.check_ready()
        except Exception:
            ACTIVITY_FAILURES.labels(
                service=self._service.service_name, stage="readiness"
            ).inc()
            raise WebResearchError("activity_unavailable") from None

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        service = self._service
        portable = self._binding.portable_context
        if not portable.user_id:
            raise WebResearchError("rejected")
        request_id = str(uuid4())
        started = time.monotonic()
        try:
            async with asyncio.timeout(5):
                await service.store.begin(
                    request_id=request_id,
                    user_id=portable.user_id,
                    session_id=portable.session_id,
                    team_id=portable.team_id,
                    agent_instance_id=self._binding.runtime_context.agent_instance_id,
                    correlation_id=portable.correlation_id,
                    operation=request.operation,
                    query=getattr(request, "query", None),
                    url=activity_url(getattr(request, "url", None)),
                )
        except Exception:
            ACTIVITY_FAILURES.labels(
                service=self._service.service_name, stage="begin"
            ).inc()
            raise WebResearchError("activity_unavailable") from None
        result: WebResearchResult | None = None
        error: WebResearchError | None = None
        cancelled = False
        try:
            async with asyncio.timeout(service.config.timeout_seconds):
                quota = await service.quota(portable.user_id, request.operation)
                if service._slots.locked():
                    raise WebResearchError("busy")
                async with service._slots:
                    result = await service.research.execute(request)
                result = result.model_copy(update={"daily_quota": quota})
        except (TimeoutError, httpx.TimeoutException):
            error = WebResearchError("timed_out")
        except httpx.ProxyError as exc:
            # Only a 403 tunnel answer is a policy refusal; 407 and 5xx are outages.
            refused = str(exc).startswith("403")
            error = WebResearchError("proxy_refused" if refused else "unavailable")
        except httpx.HTTPError:
            error = WebResearchError("unavailable")
        except WebResearchError as exc:
            error = exc
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            error = WebResearchError("invalid_response")

        async def finish() -> None:
            async with asyncio.timeout(5):
                await service.store.finish(
                    request_id,
                    outcome="cancelled"
                    if cancelled
                    else "failed"
                    if error
                    else "succeeded",
                    error_code=error.code if error else None,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    result_count=len(result.results) if result else None,
                    final_url=activity_url(result.results[0].final_url)
                    if result and request.operation == "fetch_url" and result.results
                    else None,
                )

        finish_task = asyncio.create_task(finish())
        try:
            await asyncio.shield(finish_task)
        except asyncio.CancelledError:
            await finish_task
            raise
        except Exception:
            ACTIVITY_FAILURES.labels(
                service=self._service.service_name, stage="finish"
            ).inc()
            logger.error(
                "event=web_activity_write outcome=failed reason=storage_unavailable"
            )
            raise WebResearchError("activity_unavailable") from None
        REQUESTS.labels(
            service=service.service_name,
            operation=request.operation,
            outcome="cancelled"
            if cancelled
            else "busy"
            if error and error.code == "busy"
            else "failed"
            if error
            else "succeeded",
        ).inc()
        DURATION.labels(
            service=service.service_name, operation=request.operation
        ).observe(time.monotonic() - started)
        # Content-free admin analytics: no query, URL or page text in the KPI index.
        billable = request.operation != "fetch_url" and result is not None
        runtime = get_runtime_context_or_none()
        if runtime is not None:
            runtime.get_kpi_writer().emit(
                name="web_research.request",
                type="timer",
                value=(time.monotonic() - started) * 1000,
                unit="ms",
                dims={
                    "tool_name": request.operation,
                    "status": "cancelled" if cancelled else "error" if error else "ok",
                    "error_code": error.code if error else None,
                    "team_id": portable.team_id,
                },
                cost={"usd": service.config.cost_per_1000_searches / 1000}
                if billable
                else None,
                actor=KPIActor(type="human", user_id=portable.user_id),
            )
        if cancelled:
            raise asyncio.CancelledError()
        if error is not None:
            raise error from None
        if result is None:
            raise WebResearchError("invalid_response")
        return result
