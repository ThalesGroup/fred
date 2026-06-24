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

"""Guard tests for the dependency-aware readiness probe.

These lock in the observability contract: /ready actively probes every backend and
reports which one is down (503) instead of silently hanging or always returning ok.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from knowledge_flow_backend.core.monitoring.monitoring_controller import MonitoringController


class _AsyncCM:
    """Minimal async context manager yielding a fake DB connection."""

    def __init__(self, conn: object) -> None:
        self._conn = conn

    async def __aenter__(self) -> object:
        return self._conn

    async def __aexit__(self, *_: object) -> bool:
        return False


def _healthy_context() -> SimpleNamespace:
    conn = SimpleNamespace(execute=AsyncMock(return_value=None))
    engine = MagicMock()
    engine.connect = MagicMock(return_value=_AsyncCM(conn))

    opensearch = MagicMock()
    opensearch.ping = MagicMock(return_value=True)

    rebac = MagicMock()
    rebac.get_client = AsyncMock(return_value=MagicMock())

    gcs_fs = MagicMock()
    gcs_fs.health_check = MagicMock(return_value={"backend": "gcs", "bucket": "fs"})
    gcs_content = MagicMock()
    gcs_content.health_check = MagicMock(return_value={"backend": "gcs", "buckets": ["docs", "objs"]})

    return SimpleNamespace(
        get_pg_async_engine=lambda: engine,
        get_opensearch_client=lambda: opensearch,
        get_rebac_engine=lambda: rebac,
        get_filesystem=lambda: gcs_fs,
        get_content_store=lambda: gcs_content,
    )


def _client(ctx: object) -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/knowledge-flow/v1")
    MonitoringController(router, ctx)
    app.include_router(router)
    return TestClient(app)


def test_healthz_is_trivial_ok() -> None:
    with _client(_healthy_context()) as client:
        resp = client.get("/knowledge-flow/v1/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_all_dependencies_ok() -> None:
    with _client(_healthy_context()) as client:
        resp = client.get("/knowledge-flow/v1/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    for name in ("postgres", "opensearch", "openfga", "gcs_filesystem", "gcs_content_store"):
        assert body["checks"][name]["ok"] is True


def test_ready_reports_degraded_when_gcs_down() -> None:
    ctx = _healthy_context()
    failing = MagicMock()
    failing.health_check = MagicMock(side_effect=RuntimeError("GCS bucket unreachable"))
    ctx.get_content_store = lambda: failing

    with _client(ctx) as client:
        resp = client.get("/knowledge-flow/v1/ready")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["gcs_content_store"]["ok"] is False
    assert "GCS bucket unreachable" in body["checks"]["gcs_content_store"]["error"]
    # other dependencies still report healthy
    assert body["checks"]["postgres"]["ok"] is True


def test_ready_skips_non_gcs_backend() -> None:
    ctx = _healthy_context()
    local_fs = SimpleNamespace()  # no health_check attribute → skipped, not failed
    ctx.get_filesystem = lambda: local_fs

    with _client(ctx) as client:
        resp = client.get("/knowledge-flow/v1/ready")

    assert resp.status_code == 200
    assert ctx is not None
    fs_check = resp.json()["checks"]["gcs_filesystem"]
    assert fs_check["ok"] is True
    assert "skipped" in fs_check


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
