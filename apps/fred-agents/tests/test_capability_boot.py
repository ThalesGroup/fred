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
Capability boot invariant for the PPT-filler port (#1903).

Why this test exists:
- the pod boots by discovering installed `fred.capabilities` packages and then
  validating the registry once (`fred_runtime.capabilities.registry`); a broken
  registration must fail startup loudly, so the happy-path boot for the three
  capabilities this pod ships (`demo_echo`, `document_access`, `ppt_filler`)
  is worth pinning as a fast, dependency-free unit test
- `ppt_filler` is the port's new arrival: it must contribute both its router
  (auto-mounted under `/capabilities/ppt_filler`) and its `PptPreviewPart`
  chat part (folded into the `UiPart` union at `validate()` time), and it must
  be reachable through the installed entry-point `discover()` path

The `ppt_filler` package is installed in this project's environment; the
entry-point discovery test is expected to find it (no skip guard).
"""

from __future__ import annotations

from fred_capability_ppt_filler.capability import PptFillerCapability
from fred_runtime.capabilities.demo import DemoEchoCapability
from fred_runtime.capabilities.document_access import DocumentAccessCapability
from fred_runtime.capabilities.registry import CapabilityRegistry

_PPT_PREVIEW_PART_KIND = "ppt_preview"


def _registry_with_three() -> CapabilityRegistry:
    """Register the three capabilities this pod ships, unvalidated."""

    registry = CapabilityRegistry()
    registry.register(DemoEchoCapability())
    registry.register(DocumentAccessCapability())
    registry.register(PptFillerCapability())
    return registry


def test_three_capabilities_register_and_validate() -> None:
    registry = _registry_with_three()

    # An empty env must not trip `_validate_required_env`: none of the three
    # shipped capabilities may declare a required env var (RFC §7.2), otherwise
    # a bare pod boot would fail.
    registry.validate({})

    assert registry.ids() == ("demo_echo", "document_access", "ppt_filler")
    assert "ppt_filler" in registry


def test_ppt_filler_contributes_router() -> None:
    registry = _registry_with_three()

    router_ids = [cap_id for cap_id, _router in registry.routers()]

    # ppt_filler ships a router (auto-mounted under /capabilities/ppt_filler,
    # RFC §9.1); document_access ships none, so it must be absent.
    assert "ppt_filler" in router_ids
    assert "document_access" not in router_ids


def test_ppt_filler_contributes_ppt_preview_chat_part() -> None:
    registry = _registry_with_three()

    part_names = {part.__name__ for part in registry.chat_parts()}

    assert "PptPreviewPart" in part_names


def test_ppt_preview_part_folds_into_ui_part_union_on_validate() -> None:
    from fred_sdk.contracts.capability import chat_part_kind

    registry = _registry_with_three()
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
