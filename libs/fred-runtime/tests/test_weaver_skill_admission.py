# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Real HTTP admission and local source checks; no external models or services."""

from pathlib import Path
from typing import Any

import pytest
from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_runtime.app import agent_app
from fred_runtime.app.config import LocalRuntimeFilesystemConfig
from fred_runtime.skills.catalog import PlatformSkills, admitted_skills
from fred_sdk.contracts.models import DeepAgentDefinition, ReActPolicy
from test_graph_executor_storage import _Agent as StorageGraph
from test_history import _build_config, _PingAgent
from test_platform_skills import Model, skill
from weaver_fixtures import INSTANCE_ID, SPACE_ID, create_managed_app, managed_payload

pytestmark = pytest.mark.usefixtures("offline_pod_infrastructure")


class Deep(DeepAgentDefinition):
    agent_id: str = "test.skills.deep"
    role: str = "Assistant"
    description: str = "Admitted skills"

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template="Use the admitted procedures.")


@pytest.mark.parametrize("deep", [False, True])
@pytest.mark.parametrize("project", [False, True])
def test_metadata_admission_revocation_and_replica_drift(
    monkeypatch, tmp_path, deep, project
):
    source = PlatformSkills.from_directory("package")
    graph = next(s for s in source.catalog.skills if s.name == "graph")
    decision = source.catalog.model_copy(update={"skills": (graph,)})
    model = Model()

    class Factory:
        def build(self, *_args):
            return model

    monkeypatch.setattr(agent_app, "_build_chat_model_factory", lambda _: Factory())
    config = _build_config(tmp_path)
    config.storage.object_store = LocalRuntimeFilesystemConfig(
        root=str(tmp_path / "files")
    )
    definition = Deep() if deep else _PingAgent()

    def resolved(data):
        data["skills"] = decision.model_dump(mode="json")
        if project:
            data["space"].update(
                kind="project",
                project_id=SPACE_ID,
                team_id="00000000-0000-0000-0000-000000000099",
            )

    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=config,
        binding_transform=resolved,
    )
    with TestClient(
        app, headers={"Authorization": "Bearer test-person-token"}
    ) as client:
        params = {"space_id": SPACE_ID, "agent_instance_id": INSTANCE_ID}
        metadata = client.get("/pod/v1/agents/skills", params=params)
        assert metadata.status_code == 200, metadata.text
        assert [s["name"] for s in metadata.json()["skills"]] == ["graph"]
        preview = client.get("/pod/v1/agents/skills/graph", params=params)
        assert preview.status_code == 200, preview.text
        assert "references/mermaid.md" in preview.json()["content"]
        assert model.calls == []
        assert all(request.method == "GET" for request in app.state.resolver_requests)

        def execute(name="graph"):
            body = managed_payload(
                {
                    "input": f"/{name} Draw a process",
                    "runtime_context": {"skills": [{"name": name}]},
                }
            )
            body["runtime_context"].pop("team_id")
            return client.post("/pod/v1/agents/execute", json=body)

        for name in ("mermaid", "verify-answer", "compare-options", "meeting-minutes"):
            assert execute(name).status_code == 422
        assert model.calls == []
        result = execute()
        assert result.status_code == 200, result.text
        assert len(model.calls) == 1
        assert "graph" in str(model.calls[0])
        # A newly resolved empty ceiling is authoritative for the next request.
        decision = decision.model_copy(update={"skills": ()})
        assert execute().status_code == 422
        assert len(model.calls) == 1
        assert (
            client.get("/pod/v1/agents/skills/graph", params=params).status_code == 404
        )
        decision = source.catalog.model_copy(
            update={"skills": (graph,), "revision": "0" * 64}
        )
        assert (
            client.get("/pod/v1/agents/skills/graph", params=params).status_code == 409
        )
        assert execute().status_code == 422
        # ReAct/Deep still verify an admitted snapshot without a user selection.
        ordinary: dict[str, Any] = managed_payload({"input": "ordinary turn"})
        ordinary["runtime_context"].pop("team_id")
        refused = client.post("/pod/v1/agents/execute", json=ordinary)
        assert refused.status_code == 422
        assert refused.json()["detail"] == (
            "Skill source changed or is unavailable; refresh the pod inventory"
        )
        assert len(model.calls) == 1


def test_custom_sources_obey_the_same_whitelist_and_metadata_identity(tmp_path: Path):
    skill(tmp_path, "graph", "graph")
    source = PlatformSkills.from_directory(str(tmp_path))
    assert not source.catalog.skills[0].builtin
    denied = admitted_skills(source, None)
    assert isinstance(denied, PlatformSkills) and not denied.catalog.skills
    assert not denied.filesystem_backend.contents
    accepted = admitted_skills(source, source.catalog)
    assert accepted is source
    forged = source.catalog.model_copy(
        update={
            "skills": (source.catalog.skills[0].model_copy(update={"builtin": True}),)
        }
    )
    with pytest.raises(ValueError, match="metadata"):
        admitted_skills(source, forged)


def test_unavailable_directory_is_not_an_empty_available_catalog(tmp_path: Path):
    unavailable = PlatformSkills.from_directory(str(tmp_path / "missing"))
    assert unavailable.catalog.availability == "unavailable"
    assert not unavailable.catalog.skills
    available = PlatformSkills.from_directory(str(tmp_path))
    assert available.catalog.availability == "available"
    assert not available.catalog.skills


def test_graph_execution_ignores_unused_skill_drift_but_refuses_selection(
    monkeypatch, tmp_path
):
    source = PlatformSkills.from_directory("package")
    graph = next(s for s in source.catalog.skills if s.name == "graph")
    decision = source.catalog.model_copy(
        update={"skills": (graph,), "revision": "0" * 64}
    )
    definition = StorageGraph()
    model = ToolFriendlyFakeChatModel(responses=[])
    monkeypatch.setattr(
        agent_app, "_build_chat_model_factory", lambda _: StaticChatModelFactory(model)
    )
    config = _build_config(tmp_path)

    def resolved(data):
        data["skills"] = decision.model_dump(mode="json")

    app = create_managed_app(
        monkeypatch,
        registry={definition.agent_id: definition},
        config=config,
        binding_transform=resolved,
    )
    with TestClient(
        app, headers={"Authorization": "Bearer test-person-token"}
    ) as client:
        params = {"space_id": SPACE_ID, "agent_instance_id": INSTANCE_ID}
        metadata = client.get("/pod/v1/agents/skills", params=params)
        assert metadata.status_code == 200, metadata.text
        assert not metadata.json()["supported"]
        assert (
            client.get("/pod/v1/agents/skills/graph", params=params).status_code == 404
        )
        body: dict[str, Any] = managed_payload({"input": "ordinary graph turn"})
        result = client.post("/pod/v1/agents/execute", json=body)
        assert result.status_code == 200, result.text
        assert "ok: ordinary graph turn" in result.text
        body["runtime_context"]["skills"] = [{"name": "graph"}]
        refused = client.post("/pod/v1/agents/execute", json=body)
        assert refused.status_code == 422
        assert refused.json()["detail"] == "Skills unavailable for this agent"
