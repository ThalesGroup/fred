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

Public settings travel, scope-private ones are reset for every snapshot import,
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
    unclassified_reference_fields,
    unclassified_reference_specs,
)
from fred_sdk.contracts.models import FieldSpec, TuningValue
from fred_sdk.contracts.runtime import AgentAssetPort
from pydantic import BaseModel, ValidationError

from .assets import enforce_asset_slots
from .errors import CapabilityError

MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_FILES = 128


class CapabilityCopyRejectedError(ValueError):
    """The capability cannot prepare this config for the destination."""


class ExternalAssetSaveUnavailable(AgentAssetPort):
    """Snapshot preflight cannot write through a historical workspace adapter.

    Weaver's content owners stage and accept originals after this validation.
    A capability requiring another storage mechanism must reject explicitly.
    """

    async def store(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        raise CapabilityCopyRejectedError(
            "This capability requires an unsupported external asset save"
        )

    async def fetch(self, key: str) -> bytes:
        raise CapabilityCopyRejectedError(
            "The exported package is missing a configuration file"
        )

    async def delete(self, key: str) -> None:
        raise CapabilityCopyRejectedError(
            "Snapshot validation cannot delete configuration files"
        )


def export_tuning_values(
    fields: list[FieldSpec], values: dict[str, TuningValue]
) -> dict[str, TuningValue]:
    """The template owns field classification; never export unknown saved fields."""
    if unclassified_reference_specs(fields) or set(values) - {
        field.key for field in fields
    }:
        raise CapabilityCopyRejectedError(
            "Agent fields must declare their scope before export"
        )
    return {
        field.key: values[field.key]
        for field in fields
        if field.key in values and not field.scope_private
    }


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
            extras = stored.__pydantic_extra__ or {}
            if set(extras) - {field.key for field in manifest.config_fields}:
                raise ValueError(
                    "Unknown dynamic configuration fields cannot be exported"
                )
            # Typed fields own their classification; specs classify dynamic extras.
            dynamic_specs = [
                field
                for field in manifest.config_fields
                if field.key not in type(stored).model_fields
            ]
            if unclassified_reference_fields(
                type(stored)
            ) or unclassified_reference_specs(dynamic_specs):
                raise ValueError(
                    "Configuration references must declare their scope before export"
                )
            stored = reset_scope_private(stored, field_specs=manifest.config_fields)
        config = capability.ConfigModel.model_validate(stored.model_dump(mode="json"))
    except (ValidationError, ValueError) as exc:
        raise CapabilityCopyRejectedError(
            f"Stored configuration of '{manifest.id}' cannot be read: {exc}"
        ) from exc
    return stored, config


def _decode_files(
    capability: AgentCapability[Any, Any, Any],
    keys_by_slot: Mapping[str, list[str]],
    asset_files: Mapping[str, str],
) -> dict[str, bytes]:
    manifest = capability.manifest
    if len(asset_files) > MAX_PACKAGE_FILES or sum(
        map(len, asset_files.values())
    ) > 4 * ((MAX_PACKAGE_BYTES + 2) // 3):
        raise CapabilityCopyRejectedError("Configuration files exceed export bounds")
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
    if (
        set(files) != set(asset_files)
        or sum(map(len, files.values())) > MAX_PACKAGE_BYTES
    ):
        raise CapabilityCopyRejectedError(
            "Unexpected configuration files or excessive package size"
        )
    return files


async def prepare_capability_copy(
    capability: AgentCapability[Any, Any, Any],
    request: CapabilityConfigCopyRequest,
    *,
    target_ctx: SaveContext,
) -> CapabilityConfigCopyResult:
    """Return the destination's stored config, or raise `CapabilityCopyRejectedError`."""

    manifest = capability.manifest
    # A fresh notices list per call: the capability appends what an editor must redo.
    target_ctx = replace(target_ctx, copied_from_another_scope=True, notices=[])
    stored, config = _read_stored(capability, request.config, reset=True)

    keys_by_slot = asset_keys(stored)
    files = _decode_files(capability, keys_by_slot, request.asset_files)
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
) -> CapabilityConfigExportResult:
    """Return the config as it would leave its scope, with its files inline."""

    stored, _ = _read_stored(capability, request.config, reset=True)
    keys_by_slot = asset_keys(stored)
    if request.files_by_slot:
        if set(request.files_by_slot) != set(keys_by_slot) or any(
            len(request.files_by_slot[slot]) != len(keys)
            for slot, keys in keys_by_slot.items()
        ):
            raise CapabilityCopyRejectedError(
                "Configuration files do not match the capability's asset slots"
            )
        supplied = {
            key: content
            for slot, keys in keys_by_slot.items()
            for key, content in zip(keys, request.files_by_slot[slot], strict=True)
        }
        files = _decode_files(capability, keys_by_slot, supplied)
    else:
        files = _decode_files(capability, keys_by_slot, {})
    return CapabilityConfigExportResult(
        schema_version=capability.manifest.version,
        config=stored.model_dump(mode="json"),
        files={
            key: base64.b64encode(content).decode("ascii")
            for key, content in files.items()
        },
    )
