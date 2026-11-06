# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Idempotent import of legacy PPT analyses into the shared preparation tables."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid5

from fred_core.filesystem.structures import BaseFilesystem
from fred_core.store.base_content_store import ContentStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
    CapabilityPlatformSelectionRow,
)

PPT_CAPABILITY_ID = "ppt_builder"
PPT_TEMPLATE_SLOT = "template"
LEGACY_PLATFORM_ID = "__platform__"
LEGACY_CANDIDATE_ID = "__platform_next__"
LEGACY_BUILTIN_ID = "__builtin__"
_IMPORT_NAMESPACE = UUID("79c7f083-6b73-4722-926f-b811cd01b236")


@dataclass(frozen=True)
class LegacyPptAnalysis:
    agent_instance_id: str
    team_id: str
    template_sha256: str
    labelling_key: str
    analysis_version: int
    status: str
    job_id: str
    attempts: int
    template_pptx: bytes
    inventory_json: str | None
    patterns_pdf: bytes | None
    error: str | None
    template_filename: str | None
    overrides_json: str | None
    created_at: datetime
    updated_at: datetime


def _overrides(raw: str | None) -> list[dict[str, object]]:
    value = json.loads(raw) if raw else []
    if (
        not isinstance(value, list)
        or len(value) > 256
        or any(not isinstance(item, dict) for item in value)
    ):
        raise ValueError("Invalid legacy PPT overrides")
    return value


async def import_legacy_ppt_analysis(
    session: AsyncSession,
    *,
    legacy: LegacyPptAnalysis,
    runtime_id: str,
    rules_version: str,
    content_store: ContentStore,
    artifacts: BaseFilesystem,
) -> str:
    """Import one row; returns imported, existing, skipped or a reasoned error."""
    owner = legacy.agent_instance_id
    is_platform = owner in (LEGACY_PLATFORM_ID, LEGACY_CANDIDATE_ID)
    if owner == LEGACY_BUILTIN_ID:
        return "skipped_builtin"
    if not is_platform:
        instance = await session.get(AgentInstanceRow, owner, with_for_update=True)
        if instance is None:
            return "skipped_deleted_agent"
        if (
            instance.team_id != legacy.team_id
            or instance.source_runtime_id != runtime_id
        ):
            raise ValueError("Legacy PPT owner does not match the current agent")
        if not instance.tuning_json:
            return "skipped_unconfigured_agent"
        tuning = ManagedAgentTuning.model_validate_json(instance.tuning_json)
        envelope = tuning.capability_config.get(PPT_CAPABILITY_ID)
        config = (envelope or {}).get("config") or {}
        if config.get("template_sha256") != legacy.template_sha256:
            return "skipped_changed_agent"
        use_vision = config.get("use_vision") is not False
        current = await session.scalar(
            select(CapabilityPreparationRow)
            .where(
                CapabilityPreparationRow.owner_kind == "agent",
                CapabilityPreparationRow.owner_id == owner,
                CapabilityPreparationRow.capability_id == PPT_CAPABILITY_ID,
                CapabilityPreparationRow.is_current.is_(True),
            )
            .with_for_update()
        )
        if current is not None:
            return "existing"
        owner_kind = "agent"
        preparation_owner = owner
    else:
        use_vision = legacy.labelling_key.startswith("vision:")
        owner_kind = "platform"
        preparation_owner = ""

    if not legacy.template_pptx or len(legacy.template_pptx) > 64 * 1024 * 1024:
        raise ValueError("Legacy PPT template is empty or too large")
    if owner == LEGACY_PLATFORM_ID and legacy.status != "succeeded":
        raise ValueError("Legacy platform default is not ready")
    if owner == LEGACY_CANDIDATE_ID and legacy.status == "succeeded":
        raise ValueError("Legacy platform replacement must be reconciled first")
    actual_hash = hashlib.sha256(legacy.template_pptx).hexdigest()
    if actual_hash != legacy.template_sha256:
        raise ValueError("Legacy PPT template hash mismatch")
    if legacy.inventory_json is not None:
        if len(legacy.inventory_json.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Legacy PPT inventory is too large")
        parsed = json.loads(legacy.inventory_json)
        if (
            not isinstance(parsed, dict)
            or not isinstance(parsed.get("slide_width"), int)
            or not isinstance(parsed.get("slide_height"), int)
            or not isinstance(parsed.get("patterns"), list)
        ):
            raise ValueError("Legacy PPT inventory is invalid")
    if legacy.patterns_pdf is not None and len(legacy.patterns_pdf) > 64 * 1024 * 1024:
        raise ValueError("Legacy PPT preview is too large")

    prep_id = str(
        uuid5(
            _IMPORT_NAMESPACE,
            f"{runtime_id}:{owner}:{legacy.job_id}:{legacy.template_sha256}",
        )
    )
    if await session.get(CapabilityPreparationRow, prep_id) is not None:
        return "existing"
    asset_id = str(uuid5(_IMPORT_NAMESPACE, f"asset:{prep_id}"))
    if is_platform:
        selection = await session.get(
            CapabilityPlatformSelectionRow,
            (runtime_id, PPT_CAPABILITY_ID, PPT_TEMPLATE_SLOT),
            with_for_update=True,
        )
        if selection is None:
            selection = CapabilityPlatformSelectionRow(
                runtime_id=runtime_id,
                capability_id=PPT_CAPABILITY_ID,
                slot_key=PPT_TEMPLATE_SLOT,
                settings_json={},
            )
            session.add(selection)
            await session.flush()
        pointer = (
            selection.active_preparation_id
            if owner == LEGACY_PLATFORM_ID
            else selection.candidate_preparation_id
        )
        if pointer is not None:
            return "existing"
        preparation_owner = f"platform:{prep_id}"

    asset_key = f"capability-assets/{asset_id}"
    await asyncio.to_thread(
        content_store.put_object,
        asset_key,
        io.BytesIO(legacy.template_pptx),
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    state = (
        "succeeded"
        if legacy.status == "succeeded" and legacy.inventory_json is not None
        else "failed"
        if legacy.status == "failed"
        else "pending"
    )
    reference = None
    if state == "succeeded":
        prefix = f"capability-results/{prep_id}/1/"
        await artifacts.mkdir(prefix.rstrip("/"))
        await artifacts.write(prefix + "template.pptx", legacy.template_pptx)
        await artifacts.write(prefix + "inventory.json", legacy.inventory_json or "")
        if legacy.patterns_pdf is not None:
            await artifacts.write(prefix + "patterns.pdf", legacy.patterns_pdf)
        reference = prefix + "inventory.json"

    session.add(
        CapabilityAssetRow(
            id=asset_id,
            owner_kind=owner_kind,
            owner_id=preparation_owner,
            team_id=None if is_platform else legacy.team_id,
            runtime_id=runtime_id,
            capability_id=PPT_CAPABILITY_ID,
            slot_key=PPT_TEMPLATE_SLOT,
            sha256=actual_hash,
            filename=(legacy.template_filename or "template.pptx")[:255],
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            size=len(legacy.template_pptx),
            object_key=asset_key,
            state="stored",
        )
    )
    session.add(
        CapabilityPreparationRow(
            id=prep_id,
            owner_kind=owner_kind,
            owner_id=preparation_owner,
            team_id=None if is_platform else legacy.team_id,
            runtime_id=runtime_id,
            capability_id=PPT_CAPABILITY_ID,
            input_revision=str(uuid5(_IMPORT_NAMESPACE, f"revision:{prep_id}")),
            rules_version=rules_version,
            config_json={
                "use_vision": use_vision,
                **({} if is_platform else {"template_sha256": actual_hash}),
            },
            public_config_json={"use_vision": use_vision},
            gates_readiness=not is_platform,
            is_current=True,
            state=state,
            attempts=1 if state == "succeeded" else 0,
            max_attempts=3,
            deadline_at=utcnow() + timedelta(minutes=20),
            workflow_id=f"capability-preparation/{prep_id}",
            task_queue=f"capability-preparation-{runtime_id}",
            result_reference=reference,
            error_code="legacy_analysis_failed" if state == "failed" else None,
            error_detail=(legacy.error or "")[:2000] if state == "failed" else None,
            created_at=legacy.created_at,
            completed_at=legacy.updated_at if state != "pending" else None,
        )
    )
    await session.flush()
    session.add(
        CapabilityPreparationAssetRow(
            preparation_id=prep_id, position=0, asset_id=asset_id
        )
    )
    if is_platform:
        if owner == LEGACY_PLATFORM_ID:
            selection.active_preparation_id = prep_id
            selection.settings_json = {"overrides": _overrides(legacy.overrides_json)}
        else:
            selection.candidate_preparation_id = prep_id
    return "imported"


async def import_legacy_builtin_overrides(
    session: AsyncSession, *, runtime_id: str, overrides_json: str | None
) -> None:
    selection = await session.get(
        CapabilityPlatformSelectionRow,
        (runtime_id, PPT_CAPABILITY_ID, PPT_TEMPLATE_SLOT),
        with_for_update=True,
    )
    if selection is None:
        selection = CapabilityPlatformSelectionRow(
            runtime_id=runtime_id,
            capability_id=PPT_CAPABILITY_ID,
            slot_key=PPT_TEMPLATE_SLOT,
            settings_json={},
        )
        session.add(selection)
    if selection.active_preparation_id is None and not selection.settings_json:
        selection.settings_json = {"overrides": _overrides(overrides_json)}
