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
Prepare one capability's stored config for a copied or exported agent instance.

Public settings travel, scope-private ones are reset when the scope changes,
and configuration files are re-submitted to the capability's own save in the
destination, as if an editor had uploaded them there. An export captures the
reset config and its files, so a later copy never reads the source again.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityConfigCopyRequest,
    CapabilityConfigCopyResult,
    CapabilityConfigExportRequest,
    CapabilityConfigExportResult,
    SaveContext,
    StoredCapabilityConfig,
    UploadedFile,
    asset_keys,
    reset_scope_private,
)
from pydantic import BaseModel, ValidationError

from .assets import enforce_asset_slots
from .errors import CapabilityError


class CapabilityCopyRejectedError(ValueError):
    """The capability cannot prepare this config for the destination."""


def _read_stored(
    capability: AgentCapability[Any, Any, Any],
    envelope: StoredCapabilityConfig,
    *,
    reset: bool,
) -> tuple[BaseModel, BaseModel]:
    """Upgrade the envelope, reset scope-private settings when asked; (stored, config)."""

    manifest = capability.manifest
    try:
        stored = capability.upgrade_config(envelope.config, envelope.schema_version)
        if reset:
            stored = reset_scope_private(stored, field_specs=manifest.config_fields)
        config = capability.ConfigModel.model_validate(stored.model_dump(mode="json"))
    except (ValidationError, ValueError) as exc:
        raise CapabilityCopyRejectedError(
            f"Stored configuration of '{manifest.id}' cannot be read: {exc}"
        ) from exc
    return stored, config


async def _fetch_files(
    capability: AgentCapability[Any, Any, Any],
    keys_by_slot: Mapping[str, list[str]],
    source_ctx: SaveContext,
) -> dict[str, bytes]:
    if not keys_by_slot:
        return {}
    manifest = capability.manifest
    assets = source_ctx.services.agent_assets
    if assets is None:
        raise CapabilityCopyRejectedError(
            f"Configuration files of '{manifest.id}' cannot be read on this pod."
        )
    files: dict[str, bytes] = {}
    for keys in keys_by_slot.values():
        for key in keys:
            try:
                files[key] = await assets.fetch(key)
            except Exception as exc:  # noqa: BLE001 - any read failure rejects this capability only
                raise CapabilityCopyRejectedError(
                    f"Configuration file '{key}' of '{manifest.id}' cannot be read: {exc}"
                ) from exc
    return files


def _decode_files(
    capability: AgentCapability[Any, Any, Any],
    keys_by_slot: Mapping[str, list[str]],
    asset_files: Mapping[str, str],
) -> dict[str, bytes]:
    manifest = capability.manifest
    files: dict[str, bytes] = {}
    for keys in keys_by_slot.values():
        for key in keys:
            if key not in asset_files:
                raise CapabilityCopyRejectedError(
                    f"Configuration file '{key}' of '{manifest.id}' is missing."
                )
            try:
                files[key] = base64.b64decode(asset_files[key], validate=True)
            except (binascii.Error, ValueError) as exc:
                raise CapabilityCopyRejectedError(
                    f"Configuration file '{key}' of '{manifest.id}' cannot be read: {exc}"
                ) from exc
    return files


async def prepare_capability_copy(
    capability: AgentCapability[Any, Any, Any],
    request: CapabilityConfigCopyRequest,
    *,
    source_ctx: SaveContext,
    target_ctx: SaveContext,
) -> CapabilityConfigCopyResult:
    """Return the destination's stored config, or raise `CapabilityCopyRejectedError`."""

    manifest = capability.manifest
    other_scope = request.source_team_id != request.target_team_id
    # A fresh notices list per call: the capability appends what an editor must redo.
    target_ctx = replace(target_ctx, copied_from_another_scope=other_scope, notices=[])
    stored, config = _read_stored(capability, request.config, reset=other_scope)

    keys_by_slot = asset_keys(stored)
    if request.asset_files is not None:
        files = _decode_files(capability, keys_by_slot, request.asset_files)
    else:
        files = await _fetch_files(capability, keys_by_slot, source_ctx)
    uploads: dict[str, list[UploadedFile]] = {}
    for slot, keys in keys_by_slot.items():
        for key in keys:
            uploads.setdefault(slot, []).append(
                UploadedFile(filename=key.rsplit("/", 1)[-1], content=files[key])
            )

    try:
        enforce_asset_slots(manifest, uploads)
        result = await capability.validate_config(config, uploads, target_ctx)
    except (ValidationError, ValueError, CapabilityError) as exc:
        raise CapabilityCopyRejectedError(
            f"Capability '{manifest.id}' rejected the configuration: {exc}"
        ) from exc
    return CapabilityConfigCopyResult(
        schema_version=manifest.version,
        config=result.model_dump(mode="json"),
        notices=list(target_ctx.notices),
    )


async def prepare_capability_export(
    capability: AgentCapability[Any, Any, Any],
    request: CapabilityConfigExportRequest,
    *,
    source_ctx: SaveContext,
) -> CapabilityConfigExportResult:
    """Return the config as it would leave its scope, with its files inline."""

    stored, _ = _read_stored(capability, request.config, reset=True)
    files = await _fetch_files(capability, asset_keys(stored), source_ctx)
    return CapabilityConfigExportResult(
        schema_version=capability.manifest.version,
        config=stored.model_dump(mode="json"),
        files={
            key: base64.b64encode(content).decode("ascii")
            for key, content in files.items()
        },
    )
