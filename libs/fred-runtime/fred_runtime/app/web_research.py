# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Pod-lifetime HTTPS client and per-user adapter for the web research SDK port."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import time
from uuid import uuid4

import httpx
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.web_research import (
    WebResearchDeploymentConfig,
    WebResearchError,
    WebResearchPort,
    WebResearchRequest,
    WebResearchResult,
)
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

from fred_runtime.app.web_research_activity import (
    WebResearchActivityStore,
    activity_url,
)

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
EGRESS_UP = Gauge(
    "fred_web_research_egress_up", "Authenticated HTTPS egress health", ["service"]
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
        if not config.enabled or not config.egress_url:
            raise RuntimeError(
                "Enabled web research requires an HTTPS egress endpoint."
            )
        token = os.getenv(config.token_env, "")
        if len(token) < 32:
            raise RuntimeError("Web research service credentials are required.")
        if engine.echo:
            raise RuntimeError(
                "Web research activity requires SQL statement logging to be disabled."
            )
        tls = ssl.create_default_context(cafile=config.ca_file)
        if config.client_certificate:
            tls.load_cert_chain(config.client_certificate, config.client_key)
        self.config = config
        self.service_name = service_name
        self.store = WebResearchActivityStore(engine, config.activity_retention_days)
        self.client = client or httpx.AsyncClient(
            base_url=config.egress_url + "/",
            verify=tls,
            timeout=config.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=config.max_concurrency),
            headers={"Authorization": f"Bearer {token}"},
        )
        self._slots = asyncio.Semaphore(config.max_concurrency)

    def bind(self, binding: BoundRuntimeContext) -> WebResearchPort:
        return WebResearchAdapter(self, binding)

    async def health_loop(self) -> None:
        while True:
            try:
                response = await self.client.get("health", timeout=5)
                EGRESS_UP.labels(service=self.service_name).set(
                    int(response.status_code == 200)
                )
            except Exception:
                EGRESS_UP.labels(service=self.service_name).set(0)
            await asyncio.sleep(self.config.purge_interval_seconds)

    async def close(self) -> None:
        await self.client.aclose()


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
        except WebResearchError:
            raise
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
                async with (
                    service._slots,
                    service.client.stream(
                        "POST",
                        "v1/research",
                        json=request.model_dump(),
                        headers={"X-Request-ID": request_id},
                    ) as response,
                ):
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 7_000_000:
                            raise WebResearchError("invalid_response")
                    if response.status_code != 200:
                        try:
                            code = json.loads(body).get("error_code", "unavailable")
                        except (ValueError, AttributeError):
                            code = "unavailable"
                        raise WebResearchError(code)
                    result = WebResearchResult.model_validate_json(body)
        except (TimeoutError, httpx.TimeoutException):
            error = WebResearchError("timed_out")
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
            outcome="cancelled" if cancelled else "failed" if error else "succeeded",
        ).inc()
        DURATION.labels(
            service=service.service_name, operation=request.operation
        ).observe(time.monotonic() - started)
        if cancelled:
            raise asyncio.CancelledError()
        if error is not None:
            raise error from None
        if result is None:
            raise WebResearchError("invalid_response")
        return result
