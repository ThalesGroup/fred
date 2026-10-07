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
Prepare one capability's stored config for a copied agent instance.

Public settings travel, scope-private ones are reset when the scope changes,
and configuration files are re-submitted to the capability's own save in the
destination, as if an editor had uploaded them there.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityConfigCopyRequest,
    CapabilityConfigCopyResult,
    SaveContext,
    UploadedFile,
    asset_keys,
    reset_scope_private,
)
from pydantic import ValidationError

from .assets import enforce_asset_slots
from .errors import CapabilityError


class CapabilityCopyRejectedError(ValueError):
    """The capability cannot prepare this config for the destination."""


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
    try:
        stored = capability.upgrade_config(
            request.config.config, request.config.schema_version
        )
        if other_scope:
            stored = reset_scope_private(stored, field_specs=manifest.config_fields)
        config = capability.ConfigModel.model_validate(stored.model_dump(mode="json"))
    except (ValidationError, ValueError) as exc:
        raise CapabilityCopyRejectedError(
            f"Stored configuration of '{manifest.id}' cannot be read: {exc}"
        ) from exc

    uploads: dict[str, list[UploadedFile]] = {}
    keys_by_slot = asset_keys(stored)
    if keys_by_slot:
        assets = source_ctx.services.agent_assets
        if assets is None:
            raise CapabilityCopyRejectedError(
                f"Configuration files of '{manifest.id}' cannot be read on this pod."
            )
        for slot, keys in keys_by_slot.items():
            for key in keys:
                try:
                    content = await assets.fetch(key)
                except Exception as exc:  # noqa: BLE001 - any read failure rejects this capability only
                    raise CapabilityCopyRejectedError(
                        f"Configuration file '{key}' of '{manifest.id}' cannot be read: {exc}"
                    ) from exc
                uploads.setdefault(slot, []).append(
                    UploadedFile(filename=key.rsplit("/", 1)[-1], content=content)
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
