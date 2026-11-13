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
Capability boot invariants of the fred-agents pod.

Why this test exists:
- the pod boots by discovering installed `fred.capabilities` packages and then
  validating the registry once (`fred_runtime.capabilities.registry`); a broken
  registration must fail startup loudly, so a happy-path boot of two
  representative capabilities (`document_access`, `ppt_filler`) is worth
  pinning as a fast, dependency-free unit test, and the full set of ids the
  installed packages provide is pinned at the end of this module
- `ppt_filler` is the port's new arrival: it must contribute both its router
  (auto-mounted under `/capabilities/ppt_filler`) and its `PptPreviewPart`
  chat part (folded into the `UiPart` union at `validate()` time), and it must
  be reachable through the installed entry-point `discover()` path

The `ppt_filler` package is installed in this project's environment; the
entry-point discovery test is expected to find it (no skip guard).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_capability_document_access import DocumentAccessCapability
from fred_capability_mcp import TabularCapability
from fred_capability_ppt_filler.capability import PptFillerCapability
from fred_runtime.app._catalogs import apply_external_catalog_overrides
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.capabilities.registry import (
    CapabilityRegistry,
    boot_capability_registry,
)
from fred_sdk.contracts.capability.mcp import McpServerConfig

_PPT_PREVIEW_PART_KIND = "ppt_preview"


def _registry_with_two() -> CapabilityRegistry:
    """Register two of the capabilities this pod ships, unvalidated."""

    registry = CapabilityRegistry()
    registry.register(DocumentAccessCapability())
    registry.register(PptFillerCapability())
    return registry


def test_two_capabilities_register_and_validate() -> None:
    registry = _registry_with_two()

    # An empty env must not trip `_validate_required_env`: no shipped
    # capability may declare a required env var (RFC §7.2), otherwise a bare
    # pod boot would fail.
    registry.validate({})

    assert registry.ids() == ("document_access", "ppt_filler")
    assert "ppt_filler" in registry


def test_ppt_filler_contributes_router() -> None:
    registry = _registry_with_two()

    router_ids = [cap_id for cap_id, _router in registry.routers()]

    # ppt_filler ships a router (auto-mounted under /capabilities/ppt_filler,
    # RFC §9.1); document_access ships none, so it must be absent.
    assert "ppt_filler" in router_ids
    assert "document_access" not in router_ids


def test_ppt_filler_contributes_ppt_preview_chat_part() -> None:
    registry = _registry_with_two()

    part_names = {part.__name__ for part in registry.chat_parts()}

    assert "PptPreviewPart" in part_names


def test_ppt_preview_part_folds_into_ui_part_union_on_validate() -> None:
    from fred_sdk.contracts.capability import chat_part_kind

    registry = _registry_with_two()
    registry.validate({})

    ppt_preview_part = next(
        part for part in registry.chat_parts() if part.__name__ == "PptPreviewPart"
    )
    # The chat part's discriminator kind is what `rebuild_ui_part_union` folds
    # into `UiPart`; assert the stable value the frontend renders against.
    assert chat_part_kind(ppt_preview_part) == _PPT_PREVIEW_PART_KIND


def test_discover_finds_installed_ppt_filler() -> None:
    # Installing the package IS the registration (RFC §4): the real installed
    # `fred.capabilities` entry points must include ppt_filler in this env.
    registry = CapabilityRegistry()

    discovered = registry.discover()

    assert "ppt_filler" in discovered
    assert "ppt_filler" in registry


# Every capability the pod ships today, by id — one entry per installed
# capability package. fred-runtime contributes none: it ships the framework.
# Pinned as a set so a package left out of the image (a missing Dockerfile
# COPY, a stale editable install after a directory move) fails here instead
# of silently shrinking an agent's tools.
_SHIPPED_CAPABILITY_IDS = frozenset(
    {
        "mcp-knowledge-flow-mcp-tabular",
        "document_access",
        "document_summarize",
        "document_verbatim",
        "document_extract",
        "document_similarity",
        "html_artifact",
        "open_writable_document",
        "ppt_builder",
        "ppt_filler",
        "team_wiki",
        "writable_document",
        "web_research",
    }
)


def test_discover_finds_every_shipped_capability() -> None:
    registry = CapabilityRegistry()

    discovered = registry.discover()

    assert set(discovered) == _SHIPPED_CAPABILITY_IDS


def test_default_mcp_catalog_loads_packaged_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boot from installed package metadata without a checkout config directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)
    config = apply_external_catalog_overrides(
        AgentPodConfig.model_validate(
            {
                "app": {"runtime_id": "test-pod"},
                "ai": {"knowledge_flow_url": "https://kf.example:9443/custom/v2/"},
                "security": {
                    "user": {
                        "enabled": False,
                        "realm_url": "http://localhost/r",
                        "client_id": "test",
                    },
                    "m2m": {
                        "enabled": False,
                        "realm_url": "http://localhost/r",
                        "client_id": "test",
                    },
                },
            }
        )
    )
    catalog = config.get_mcp_configuration()
    assert catalog is None
    registry = boot_capability_registry(env={})
    assert set(registry.ids()) == _SHIPPED_CAPABILITY_IDS
    tabular = registry.capability("mcp-knowledge-flow-mcp-tabular")
    assert isinstance(tabular, TabularCapability)
    assert tabular.manifest.id == "mcp-knowledge-flow-mcp-tabular"
    assert "## Tabular data access" in (tabular.prompt_group().agent_instructions or "")
    assert (
        tabular.chat_controls(
            McpServerConfig.model_validate(
                {
                    "chat_options.attach_files": True,
                    "chat_options.documents_selection": True,
                }
            )
        )[0].widget
        == "attach_files"
    )
