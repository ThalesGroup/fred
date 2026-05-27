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
"""
Observability bootstrap factory for Fred agent pods.

Why this module exists:
- the tracer and metrics provider are selected by name in configuration.yaml
- this factory translates those names into concrete instances
- it keeps agent_app.py free of provider-specific import chains
- adding a new backend means adding one branch here, nothing else changes

How to use it:
- call `bootstrap_observability(config.observability)` once during pod startup
- the global tracer and metrics provider are then set for the lifetime of the process

Configuration contract:
- backend names come from `PodObservabilityConfig` (tracer, metrics fields)
- credentials (API keys, tokens) stay in the .env file
- non-secret settings (host, paths) live in configuration.yaml

Example:
    bootstrap_observability(config.observability)
    # → set_tracer(LoggingTracer())
    # → set_metrics_provider(LoggingMetricsProvider())
"""

from __future__ import annotations

import logging
import os
from typing import cast

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.portable import (
    LoggingMetricsProvider,
    LoggingTracer,
    MetricsProvider,
    Tracer,
    set_metrics_provider,
    set_tracer,
)

from .config import MetricsBackend, PodObservabilityConfig, TracerBackend

logger = logging.getLogger(__name__)


def bootstrap_observability(
    config: PodObservabilityConfig,
    *,
    kpi_writer: BaseKPIWriter | None = None,
) -> None:
    """
    Set the global tracer and metrics provider from pod config.

    Why this exists:
    - observability must be initialized before the first log or span is emitted
    - a single call here replaces scattered hardcoded provider choices in agent_app

    How to use it:
    - call once in the FastAPI lifespan before any other startup work
    - pass `kpi_writer` when `metrics=prometheus` so portable runtime timers
      feed the same Prometheus/KPI pipeline as the execution engine
    - the choices made here propagate to every `get_tracer()` / `get_metrics_provider()`
      call in the process

    Example:
    - `bootstrap_observability(config.observability, kpi_writer=writer)`
    """
    tracer = _build_tracer(config)
    metrics = _build_metrics(config, kpi_writer=kpi_writer)
    set_tracer(tracer)
    set_metrics_provider(metrics)
    logger.info(
        "[fred-runtime] observability ready — tracer=%s metrics=%s",
        config.tracer.value,
        config.metrics.value,
    )


# ---------------------------------------------------------------------------
# Tracer builders
# ---------------------------------------------------------------------------


def _build_tracer(config: PodObservabilityConfig) -> Tracer:
    if config.tracer == TracerBackend.null:
        return Tracer()
    if config.tracer == TracerBackend.logging:
        return LoggingTracer()
    if config.tracer == TracerBackend.langfuse:
        return _build_langfuse_tracer(config)
    logger.warning(
        "[fred-runtime] Unknown tracer backend '%s' — falling back to logging",
        config.tracer,
    )
    return LoggingTracer()


def _build_langfuse_tracer(config: PodObservabilityConfig) -> Tracer:
    """
    Build the Langfuse tracer adapter.

    Why this is separate:
    - Langfuse requires optional dependencies (langfuse package)
    - if the package is missing or credentials are absent, the pod must still
      start — it falls back to LoggingTracer with a clear warning

    Credentials:
    - LANGFUSE_PUBLIC_KEY  (required, must be in .env)
    - LANGFUSE_SECRET_KEY  (required, must be in .env)
    - host comes from config.observability.langfuse.host
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        logger.warning(
            "[fred-runtime] tracer=langfuse selected but LANGFUSE_PUBLIC_KEY or"
            " LANGFUSE_SECRET_KEY is not set — falling back to logging"
        )
        return LoggingTracer()
    try:
        from fred_runtime.integrations.v2_runtime.adapters import build_langfuse_tracer

        tracer = build_langfuse_tracer()
        if tracer is None:
            logger.warning(
                "[fred-runtime] Langfuse tracer could not be built — falling back to logging"
            )
            return LoggingTracer()
        logger.info(
            "[fred-runtime] Langfuse tracer initialized (host=%s)", config.langfuse.host
        )
        return tracer
    except Exception:
        logger.exception(
            "[fred-runtime] Failed to initialize Langfuse tracer — falling back to logging"
        )
        return LoggingTracer()


# ---------------------------------------------------------------------------
# Metrics builders
# ---------------------------------------------------------------------------


def _build_metrics(
    config: PodObservabilityConfig,
    *,
    kpi_writer: BaseKPIWriter | None = None,
) -> MetricsProvider:
    if config.metrics == MetricsBackend.null:
        return MetricsProvider()
    if config.metrics == MetricsBackend.logging:
        return LoggingMetricsProvider()
    if config.metrics == MetricsBackend.prometheus:
        if kpi_writer is None:
            logger.warning(
                "[fred-runtime] metrics=prometheus selected without a KPI writer"
                " — falling back to logging"
            )
            return LoggingMetricsProvider()
        from fred_runtime.integrations.v2_runtime.adapters import (
            KPIWriterMetricsAdapter,
        )

        return cast(MetricsProvider, KPIWriterMetricsAdapter(kpi_writer))
    logger.warning(
        "[fred-runtime] Unknown metrics backend '%s' — falling back to logging",
        config.metrics,
    )
    return LoggingMetricsProvider()
