"""PPT Builder produces revision-scoped artifacts through the shared hook."""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fred_sdk.contracts.capability.preparation import (
    PreparationAsset,
    PreparationContext,
    PreparationWork,
)
from fred_sdk.contracts.capability.context import CapabilityIdentity, SaveContext
from fred_sdk.contracts.capability.manifest import UploadedFile
from fred_sdk.contracts.runtime import RuntimeServices

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
