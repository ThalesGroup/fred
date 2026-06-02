import asyncio

import pytest

from knowledge_flow_backend import main_worker as main_worker_module
from knowledge_flow_backend.application_context import ApplicationContext


@pytest.mark.asyncio
async def test_main_worker_enables_observability_from_configuration(app_context, monkeypatch) -> None:
    """
    Verify worker startup honors metrics and KPI settings from configuration.

    Why:
        The worker now exposes observability knobs through YAML, so startup must
        translate those settings into a Prometheus exporter and KPI background tasks.
    How:
        Run `main()` with patched side effects and assert the worker starts the
        metrics server, schedules KPI emitters, runs Temporal, and shuts down cleanly.
    """
    config = app_context.configuration.model_copy(deep=True)
    config.app = config.app.model_copy(
        update={
            "metrics_enabled": True,
            "kpi_process_metrics_interval_sec": 10,
        }
    )
    config.scheduler = config.scheduler.model_copy(
        update={
            "enabled": True,
            "temporal": config.scheduler.temporal.model_copy(
                update={
                    "ingestion_max_concurrent_workflow_tasks": 4,
                    "ingestion_max_concurrent_activities": 6,
                }
            ),
        }
    )

    observed: dict[str, object] = {}
    writer_sentinel = object()
    engine_sentinel = object()

    async def fake_run_worker(
        temporal_config,
        *,
        max_concurrent_workflow_tasks: int = 1,
        max_concurrent_activities: int = 1,
    ) -> None:
        """Capture the Temporal config passed to the worker and yield once."""
        observed["temporal_config"] = temporal_config
        observed["max_concurrent_workflow_tasks"] = max_concurrent_workflow_tasks
        observed["max_concurrent_activities"] = max_concurrent_activities
        await asyncio.sleep(0)

    async def fake_emit_process_kpis(interval_s: float, writer) -> None:
        """Record process KPI scheduling inputs without starting a real loop."""
        observed["process_kpi"] = (interval_s, writer)
        await asyncio.sleep(0)

    async def fake_emit_sql_pool_kpis(interval_s: float, writer, engine, pool_name: str) -> None:
        """Record SQL pool KPI scheduling inputs without touching a real database."""
        observed["sql_pool_kpi"] = (interval_s, writer, engine, pool_name)
        await asyncio.sleep(0)

    async def fake_shutdown(self) -> None:
        """Mark the test context as shut down without closing real shared resources."""
        observed["shutdown_called"] = True

    monkeypatch.setattr(main_worker_module, "load_configuration", lambda: config)
    monkeypatch.setattr(main_worker_module, "get_loaded_env_file_path", lambda: "/tmp/test.env")
    monkeypatch.setattr(main_worker_module, "get_loaded_config_file_path", lambda: "/tmp/test.yaml")
    monkeypatch.setattr(
        main_worker_module,
        "start_http_server",
        lambda port, addr: observed.setdefault("metrics_server", (port, addr)),
    )
    monkeypatch.setattr(main_worker_module, "run_worker", fake_run_worker)
    monkeypatch.setattr(main_worker_module, "emit_process_kpis", fake_emit_process_kpis)
    monkeypatch.setattr(main_worker_module, "emit_sql_pool_kpis", fake_emit_sql_pool_kpis)
    monkeypatch.setattr(ApplicationContext, "get_kpi_writer", lambda self: writer_sentinel)
    monkeypatch.setattr(ApplicationContext, "get_pg_async_engine", lambda self: engine_sentinel)
    monkeypatch.setattr(ApplicationContext, "shutdown", fake_shutdown)

    ApplicationContext.reset_instance()
    try:
        await main_worker_module.main()
    finally:
        ApplicationContext.reset_instance()

    assert observed["metrics_server"] == (config.app.metrics_port, config.app.metrics_address)
    assert observed["process_kpi"] == (10.0, writer_sentinel)
    assert observed["sql_pool_kpi"] == (10.0, writer_sentinel, engine_sentinel, "knowledge-flow-postgres")
    assert observed["temporal_config"] == config.scheduler.temporal
    assert observed["max_concurrent_workflow_tasks"] == 4
    assert observed["max_concurrent_activities"] == 6
    assert observed["shutdown_called"] is True
