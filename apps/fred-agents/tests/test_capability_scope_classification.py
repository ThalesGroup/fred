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
Guard: every identifier-like capability setting installed on this pod is
classified scope-private, public or asset key, so copying an agent to another
scope never carries a reference to the source scope's items by omission.
See docs/swift/capabilities/AUTHORING.md, "Scope-private settings".
"""

from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import pytest
import yaml
from fred_sdk.contracts.capability import (
    unclassified_reference_fields,
    unclassified_reference_specs,
)
from fred_sdk.contracts.models import FieldSpec

_REPO = Path(__file__).resolve().parents[3]
_MCP_CATALOGS = [
    _REPO / "deploy" / "charts" / "fred" / "values.yaml",
]


def _capability_classes() -> list[Any]:
    return [ep.load() for ep in entry_points(group="fred.capabilities")]


def _mcp_servers(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "servers" in payload:
            return list(payload["servers"])
        if "mcp_catalog" in payload:
            return list(payload["mcp_catalog"].get("servers", []))
        return [s for value in payload.values() for s in _mcp_servers(value)]
    return []


def test_first_party_capabilities_are_installed() -> None:
    assert len(_capability_classes()) >= 7


@pytest.mark.parametrize("capability", _capability_classes(), ids=lambda c: c.__name__)
def test_capability_settings_are_classified(capability: Any) -> None:
    offenders = {
        model.__name__: unclassified_reference_fields(model)
        for model in {capability.ConfigModel, capability.StoredConfigModel}
    }
    # A spec mirroring a typed field is classified by the model; only extra,
    # catalog-declared keys classify through the spec itself.
    typed = set(capability.ConfigModel.model_fields)
    offenders["manifest.config_fields"] = unclassified_reference_specs(
        [spec for spec in capability.manifest.config_fields if spec.key not in typed]
    )
    offenders = {name: paths for name, paths in offenders.items() if paths}
    assert not offenders, (
        f"{capability.manifest.id}: {offenders} hold identifiers but are neither "
        "ScopePrivate, Public nor AssetKey. Classify them (AUTHORING.md, "
        "'Scope-private settings')."
    )


@pytest.mark.parametrize("catalog", _MCP_CATALOGS, ids=lambda p: p.name)
def test_mcp_catalog_settings_are_classified(catalog: Path) -> None:
    servers = _mcp_servers(yaml.safe_load(catalog.read_text()))
    offenders = {
        server["id"]: unclassified_reference_specs(
            [
                FieldSpec.model_validate(field)
                for field in server.get("config_fields", [])
            ]
        )
        for server in servers
    }
    offenders = {server: keys for server, keys in offenders.items() if keys}
    assert not offenders, (
        f"{offenders} hold identifiers but declare no scope_private: true/false."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["export", "import"])
async def test_document_access_snapshot_uses_its_typed_scope_classification(operation):
    from fred_capability_document_access.capability import DocumentAccessCapability
    from fred_runtime.capabilities.copy import (
        prepare_capability_copy,
        prepare_capability_export,
    )
    from fred_sdk.contracts.capability import (
        CapabilityConfigCopyRequest,
        CapabilityConfigExportRequest,
        CapabilityIdentity,
        SaveContext,
        StoredCapabilityConfig,
    )
    from fred_sdk.contracts.runtime import RuntimeServices

    capability = DocumentAccessCapability()
    source = StoredCapabilityConfig(
        schema_version=capability.manifest.version,
        config={
            "library_tag_ids": ["00000000-0000-4000-8000-000000000001"],
            "document_uids": ["00000000-0000-4000-8000-000000000002"],
            "bind_libraries": True,
            "default_top_k": 12,
            "attachments": False,
        },
    )
    if operation == "export":
        result = await prepare_capability_export(
            capability,
            CapabilityConfigExportRequest(
                config=source,
                space_id="source",
                agent_instance_id="original",
            ),
        )
        assert result.files == {}
        imported = await prepare_capability_copy(
            capability,
            CapabilityConfigCopyRequest(
                config=StoredCapabilityConfig(
                    schema_version=result.schema_version, config=result.config
                ),
                target_space_id="target",
                target_agent_instance_id="copy",
                asset_files=result.files,
            ),
            target_ctx=SaveContext(
                identity=CapabilityIdentity(user_id="editor", space_id="target"),
                services=RuntimeServices(),
            ),
        )
        assert imported.config == result.config
    else:
        result = await prepare_capability_copy(
            capability,
            CapabilityConfigCopyRequest(
                config=source,
                target_space_id="target",
                target_agent_instance_id="copy",
                asset_files={},
            ),
            target_ctx=SaveContext(
                identity=CapabilityIdentity(user_id="editor", space_id="target"),
                services=RuntimeServices(),
            ),
        )
    assert result.config["library_tag_ids"] == []
    assert result.config["document_uids"] is None
    assert result.config["bind_libraries"] is False
    assert result.config["default_top_k"] == 12
    assert result.config["attachments"] is False
    assert source.config["bind_libraries"] is True
