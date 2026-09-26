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

"""A pod declares the library it fills, so people stop being able to write in it.

The pod sends this because it is the only party holding the right to write in
that library — Fred's own control plane holds nothing over the folder. Two
properties matter more than the call itself: a pod that keeps its own store
declares nothing, and a declaration that fails never costs the run.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import httpx
import pytest
from fred_pod.security.backend_to_backend_auth import M2MBearerAuth
from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base.documents import declare_library_synchronized

LIBRARY = "lib-1"
INSTANCE = "ab12"


def _configuration(knowledge_flow_url: str) -> PodConfiguration:
    payload: dict[str, Any] = {
        "knowledge_base": {
            "prefix": "acme.kb",
            "control_plane_url": "http://example.invalid/control-plane/v1/",
            "knowledge_flow_url": knowledge_flow_url,
        },
        "security": {
            "m2m": {
                "realm_url": "http://keycloak.invalid/realms/app",
                "client_id": "kb-local-folder",
                "secret_env_var": "ACME_KB_CLIENT_SECRET",  # pragma: allowlist secret
            }
        },
    }
    return PodConfiguration.model_validate(payload)


class _RecordingTransport:
    """Stands in for the token minter and the HTTP call behind the declaration."""

    def __init__(self, status: int = 200, text: str = "") -> None:
        self.status = status
        self.text = text
        self.calls: list[tuple[str, dict, dict]] = []
        self.auth: httpx.Auth | None = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorder = self

        class _Client:
            def __init__(self, **kwargs) -> None:
                recorder.auth = kwargs.get("auth")

            async def __aenter__(self) -> "_Client":
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def put(self, url, *, json, headers=None):
                recorder.calls.append((url, json, headers or {}))
                return httpx.Response(
                    recorder.status,
                    text=recorder.text,
                    request=httpx.Request("PUT", url),
                )

        monkeypatch.setattr(
            "fred_sdk.knowledge_base.documents.httpx.AsyncClient", _Client
        )


def test_the_pod_names_itself_and_the_library_it_fills(monkeypatch):
    transport = _RecordingTransport()
    transport.install(monkeypatch)

    asyncio.run(
        declare_library_synchronized(
            _configuration("http://kf.invalid/knowledge-flow/v1"),
            library_id=LIBRARY,
            instance_id=INSTANCE,
        )
    )

    url, body, headers = transport.calls[0]
    assert (
        url
        == f"http://kf.invalid/knowledge-flow/v1/libraries/{LIBRARY}/synchronized-by"
    )
    assert body == {"synchronized_by": f"knowledge_base:{INSTANCE}"}
    assert isinstance(transport.auth, M2MBearerAuth)


def test_a_pod_keeping_its_own_store_declares_nothing(monkeypatch):
    """Fred holds no documents for it, so there is no folder of its to close."""
    transport = _RecordingTransport()
    transport.install(monkeypatch)

    asyncio.run(
        declare_library_synchronized(
            _configuration(""), library_id=LIBRARY, instance_id=INSTANCE
        )
    )

    assert transport.calls == []


def test_a_refused_declaration_does_not_fail_the_run(monkeypatch, caplog):
    """A base that stopped synchronizing over a marker would be the worse failure."""
    transport = _RecordingTransport(status=400, text="another machine already fills it")
    transport.install(monkeypatch)

    asyncio.run(
        declare_library_synchronized(
            _configuration("http://kf.invalid/knowledge-flow/v1"),
            library_id=LIBRARY,
            instance_id=INSTANCE,
        )
    )

    assert "Fred refused the declaration" in caplog.text


def test_an_unreachable_fred_does_not_fail_the_run(monkeypatch, caplog):
    def _explode(**_kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr("fred_sdk.knowledge_base.documents.httpx.AsyncClient", _explode)

    asyncio.run(
        declare_library_synchronized(
            _configuration("http://kf.invalid/knowledge-flow/v1"),
            library_id=LIBRARY,
            instance_id=INSTANCE,
        )
    )

    assert "Could not declare library" in caplog.text


def test_the_declaration_is_sent_before_the_handler_runs(monkeypatch):
    """A run that fails halfway still filled part of the library.

    Declaring afterwards would leave that part editable for the length of the
    run, which is exactly when a source is writing into it.
    """
    from types import SimpleNamespace

    from fred_sdk.knowledge_base import worker as worker_module
    from fred_sdk.knowledge_base._workflow import SynchronizeInput
    from fred_sdk.knowledge_base.client import ControlPlaneClient
    from fred_sdk.knowledge_base.knowledge_base import KnowledgeBase
    from fred_sdk.knowledge_base.models import (
        KnowledgeBaseRunContext,
        KnowledgeBaseRunOutcome,
        KnowledgeBaseSyncResult,
    )

    order: list[str] = []

    async def _declare(configuration, *, library_id, instance_id):
        order.append(f"declare:{library_id}:{instance_id}")

    monkeypatch.setattr(worker_module, "declare_library_synchronized", _declare)

    kb = KnowledgeBase(
        id="acme.kb.thing", version="1.0.0", name="Thing", description="A thing"
    )

    @kb.synchronize
    async def _handler(context: KnowledgeBaseRunContext) -> KnowledgeBaseSyncResult:
        order.append("handler")
        return KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded,
            reconciliation_complete=True,
            summary="done",
        )

    context = KnowledgeBaseRunContext(
        definition_id="acme.kb.thing",
        instance_id=INSTANCE,
        team_id="team-1",
        run_id="run-1",
        library_id=LIBRARY,
    )

    async def _fetch(definition_id, instance_id, run_id):
        return context

    activity_fn = worker_module._build_activity(
        kb,
        cast(ControlPlaneClient, SimpleNamespace(fetch_run_context=_fetch)),
        _configuration("http://kf.invalid/knowledge-flow/v1"),
    )

    outcome = asyncio.run(
        activity_fn(SynchronizeInput("acme.kb.thing", INSTANCE, "team-1"), "run-1")
    )

    assert outcome == "succeeded"
    assert order == [f"declare:{LIBRARY}:{INSTANCE}", "handler"]
