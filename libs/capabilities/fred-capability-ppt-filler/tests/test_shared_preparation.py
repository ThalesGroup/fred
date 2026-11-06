"""PPT Builder produces revision-scoped artifacts through the shared hook."""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import httpx
from fastapi import FastAPI, HTTPException
from fred_sdk.contracts.capability.preparation import (
    PreparationAsset,
    PreparationContext,
    PreparationWork,
)
from fred_sdk.contracts.capability.context import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    SaveContext,
)
from fred_sdk.contracts.capability.manifest import UploadedFile
from fred_sdk.contracts.runtime import (
    CapabilityPreparationReader,
    CapabilityTeamAuthorizer,
    RuntimeServices,
    capability_preparation_reader,
    capability_team_authorizer,
)

from fred_capability_ppt_filler.builder import capability as builder
from fred_capability_ppt_filler.builder.builtin import builtin_template


class Artifacts:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def write(self, path: str, content: bytes) -> None:
        self.data[path] = content


@pytest.mark.asyncio
async def test_prepare_writes_inventory_preview_and_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, inventory = builtin_template()
    asset_id = uuid4()
    preparation_id = uuid4()
    work = PreparationWork(
        preparation_id=preparation_id,
        owner_kind="agent",
        owner_id="agent-1",
        runtime_id="fred-agents",
        capability_id="ppt_builder",
        input_revision="revision-1",
        rules_version="23",
        attempt=1,
        assets=(
            PreparationAsset(
                asset_id=asset_id,
                slot_key="template",
                filename="template.pptx",
                sha256=hashlib.sha256(template).hexdigest(),
                size=len(template),
            ),
        ),
        config={"use_vision": False},
    )
    artifacts = Artifacts()
    monkeypatch.setattr(
        builder,
        "analyze_template",
        lambda content: SimpleNamespace(inventory=inventory),
    )
    monkeypatch.setattr(builder, "build_patterns_deck", lambda content, parsed: b"deck")
    monkeypatch.setattr(
        builder, "convert_office_bytes_to_pdf", AsyncMock(return_value=b"%PDF")
    )
    label = AsyncMock(return_value=inventory)
    monkeypatch.setattr(builder, "label_inventory", label)
    result = await builder.PptBuilderCapability().prepare(
        PreparationContext(
            work=work,
            assets=SimpleNamespace(read=AsyncMock(return_value=template)),
            artifacts=artifacts,
        )
    )
    assert result.reference == f"capability-results/{preparation_id}/1/inventory.json"
    assert inventory.model_validate_json(artifacts.data[result.reference]) == inventory
    assert (
        artifacts.data[f"capability-results/{preparation_id}/1/patterns.pdf"] == b"%PDF"
    )
    assert artifacts.data[f"capability-results/{preparation_id}/1/template.pptx"]
    assert label.await_args.kwargs["use_vision"] is False


@pytest.mark.asyncio
async def test_shared_save_validates_template_without_legacy_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _ = builtin_template()
    monkeypatch.setattr(
        builder, "get_analysis_store", lambda: pytest.fail("legacy store accessed")
    )
    context = SaveContext(
        identity=CapabilityIdentity(user_id="editor", agent_instance_id=str(uuid4())),
        services=RuntimeServices(),
        preparation_enabled=True,
    )
    stored = await builder.PptBuilderCapability().validate_config(
        builder.PptBuilderConfig(labelling_model="legacy-profile", use_vision=False),
        {"template": [UploadedFile(filename="template.pptx", content=template)]},
        context,
    )
    assert stored.preparation_mode == "shared"
    assert stored.labelling_model is None
    assert stored.template_sha256 == hashlib.sha256(template).hexdigest()


@pytest.mark.asyncio
async def test_turn_reads_only_the_bound_preparation_revision() -> None:
    template, inventory = builtin_template()

    class BoundArtifacts:
        async def read_result(self, capability_id: str) -> bytes:
            assert capability_id == "ppt_builder"
            return inventory.model_dump_json().encode()

        async def read_sibling(self, capability_id: str, filename: str) -> bytes:
            assert (capability_id, filename) == ("ppt_builder", "template.pptx")
            return template

    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="user", agent_instance_id=str(uuid4())),
        config=builder.PptBuilderConfig(
            template_sha256=hashlib.sha256(template).hexdigest(),
            preparation_mode="shared",
            use_vision=False,
        ),
        turn_options=EmptyModel(),
        services=RuntimeServices(preparation_artifacts=BoundArtifacts()),
    )
    middleware = builder._PptBuilderMiddleware(ctx)
    assert await middleware._resolve() is not None
    assert await middleware._load_template() == template


@pytest.mark.asyncio
async def test_shared_turn_never_falls_back_to_legacy_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        builder, "get_analysis_store", lambda: pytest.fail("legacy inventory accessed")
    )
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="user", agent_instance_id=str(uuid4())),
        config=builder.PptBuilderConfig(
            template_sha256="a" * 64, preparation_mode="shared", use_vision=False
        ),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    middleware = builder._PptBuilderMiddleware(ctx)
    assert await middleware._resolve() is None


@pytest.mark.asyncio
async def test_shared_save_rejects_vision_without_knowledge_flow() -> None:
    template, _ = builtin_template()
    context = SaveContext(
        identity=CapabilityIdentity(user_id="editor", agent_instance_id=str(uuid4())),
        services=RuntimeServices(
            preparation_vision=SimpleNamespace(available=AsyncMock(return_value=False))
        ),
        preparation_enabled=True,
    )
    with pytest.raises(ValueError, match="Knowledge Flow vision is unavailable"):
        await builder.PptBuilderCapability().validate_config(
            builder.PptBuilderConfig(use_vision=True),
            {"template": [UploadedFile(filename="template.pptx", content=template)]},
            context,
        )


@pytest.mark.asyncio
async def test_shared_agent_routes_read_current_inventory_and_preview() -> None:
    template, inventory = builtin_template()
    reference = "capability-results/current/1/inventory.json"

    class Authorizer(CapabilityTeamAuthorizer):
        async def require_agent_editor(self, team_id: str) -> None:
            if team_id != "t1":
                raise HTTPException(status_code=403)

    class Reader(CapabilityPreparationReader):
        async def agent_status(self, team_id, agent_instance_id, capability_id):
            assert (team_id, agent_instance_id, capability_id) == (
                "t1",
                "a1",
                "ppt_builder",
            )
            return {
                "state": "succeeded",
                "assets": [
                    {
                        "slot_key": "template",
                        "sha256": hashlib.sha256(template).hexdigest(),
                    }
                ],
                "result_reference": reference,
                "created_at": "2026-11-06T12:00:00Z",
            }

        async def read_result(self, result_reference):
            assert result_reference == reference
            return inventory.model_dump_json().encode()

        async def read_sibling(self, result_reference, filename):
            assert (result_reference, filename) == (reference, "patterns.pdf")
            return b"%PDF"

        async def sibling_exists(self, result_reference, filename):
            return (result_reference, filename) == (reference, "patterns.pdf")

    app = FastAPI()
    router = builder.PptBuilderCapability.manifest.router
    assert router is not None
    app.include_router(router, prefix="/capabilities/ppt_builder")
    app.dependency_overrides[capability_team_authorizer] = Authorizer
    app.dependency_overrides[capability_preparation_reader] = Reader
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://pod"
    ) as client:
        response = await client.get(
            "/capabilities/ppt_builder/analysis/a1", params={"team_id": "t1"}
        )
        assert response.status_code == 200
        assert response.json()["inventory"]["patterns"]
        assert (
            response.json()["template_sha256"] == hashlib.sha256(template).hexdigest()
        )
        preview = await client.get(
            "/capabilities/ppt_builder/analysis/a1/patterns.pdf",
            params={"team_id": "t1"},
        )
        assert preview.content == b"%PDF"
