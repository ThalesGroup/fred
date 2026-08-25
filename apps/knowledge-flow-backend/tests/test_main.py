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

"""App-factory wiring of the signed object proxy (CONTENT-URL-STRATEGY, #2318).

Asserted through real requests, not `app.routes`: FastAPI keeps an included router
as a single nested entry, so scanning `app.routes` for the path silently passes
whether the route is mounted or not.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fred_core.store import make_signed_token

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import LocalContentStorageConfig
from knowledge_flow_backend.main import create_app

# Fake key: no real signing material is involved in these tests.
SECRET = "proxy-mount-test-key"  # nosec B105  # pragma: allowlist secret
OBJECT_KEY = "doc-1/output/media/diagram.png"

_STUBBED_CONTROLLERS = [
    "MonitoringController",
    "TasksController",
    "MetadataController",
    "ContentController",
    "AudioTranscriptionController",
    "IngestionController",
    "TagController",
    "VectorSearchController",
    "CorpusTreeController",
    "SummarizeController",
    "ExtractController",
    "ResourceController",
    "McpFilesystemController",
    "CorpusManagerController",
    "TabularController",
    "OpenSearchOpsController",
    "PrometheusOpsController",
    "SchedulerController",
]


def _create_app_with_url_strategy(
    app_context: ApplicationContext,
    monkeypatch: pytest.MonkeyPatch,
    root_path: Path,
    strategy: str,
):
    """Build the real app with only `content_storage` swapped, controllers stubbed."""
    config = app_context.configuration.model_copy(deep=True)
    config.content_storage = LocalContentStorageConfig(type="local", root_path=str(root_path), url_strategy=strategy)
    monkeypatch.setattr(main_module, "load_configuration", lambda: config)
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    for attr_name in _STUBBED_CONTROLLERS:
        monkeypatch.setattr(main_module, attr_name, lambda *args, **kwargs: None)
    ApplicationContext.reset_instance()
    return create_app(), config


def test_object_proxy_serves_a_signed_object_under_the_proxy_strategy(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`url_strategy=proxy` is what makes markdown media reachable without a bearer."""
    monkeypatch.setenv("KNOWLEDGE_FLOW_CONTENT_URL_SECRET", SECRET)
    stored = tmp_path / "objects" / OBJECT_KEY
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"diagram-bytes")

    app, config = _create_app_with_url_strategy(app_context, monkeypatch, tmp_path, "proxy")
    token = make_signed_token([OBJECT_KEY], secret=SECRET, ttl_seconds=60)
    try:
        # No `with`: the lifespan opens Postgres/Temporal connections these offline
        # tests must not need — routing works without it.
        client = TestClient(app)
        served = client.get(f"{config.app.base_url}/objects/{OBJECT_KEY}?token={token}")
        refused = client.get(f"{config.app.base_url}/objects/{OBJECT_KEY}?token=forged")
    finally:
        ApplicationContext.reset_instance()

    assert served.status_code == 200
    assert served.content == b"diagram-bytes"
    assert served.headers["cache-control"].startswith("private, max-age=")
    assert refused.status_code == 403


def test_object_proxy_is_absent_under_the_presigned_default(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No dormant unauthenticated route in `presigned` mode (RFC §2.4)."""
    app, config = _create_app_with_url_strategy(app_context, monkeypatch, tmp_path, "presigned")
    token = make_signed_token([OBJECT_KEY], secret=SECRET, ttl_seconds=60)
    try:
        response = TestClient(app).get(f"{config.app.base_url}/objects/{OBJECT_KEY}?token={token}")
    finally:
        ApplicationContext.reset_instance()

    assert response.status_code == 404


def test_proxy_strategy_without_a_signing_key_stops_the_boot(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The signing key is a credential: a missing one fails at startup, not at first render."""
    monkeypatch.delenv("KNOWLEDGE_FLOW_CONTENT_URL_SECRET", raising=False)

    try:
        with pytest.raises(RuntimeError, match="KNOWLEDGE_FLOW_CONTENT_URL_SECRET"):
            _create_app_with_url_strategy(app_context, monkeypatch, tmp_path, "proxy")
    finally:
        ApplicationContext.reset_instance()
