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

"""Registry boot invariants for the html_artifact capability (RFC §4, §7).

Registering the capability into a fresh `CapabilityRegistry` and calling
`.validate()` must be green: the `html_artifact` chat-part kind is unique and the
capability owns no tables/router (v1 is read-only, markup inline on the part).
"""

from __future__ import annotations

from fred_capability_html_artifact.capability import HtmlArtifactCapability
from fred_runtime.capabilities.registry import CapabilityRegistry


def test_capability_registers_and_validates_clean():
    registry = CapabilityRegistry()
    registry.register(HtmlArtifactCapability())
    # No raise = all boot invariants hold (chat-part kind unique, env, scope).
    registry.validate()
    assert "html_artifact" in registry.ids()


def test_manifest_declares_chat_part_and_side_panel_only():
    manifest = HtmlArtifactCapability.manifest
    assert [p.__name__ for p in manifest.chat_parts] == ["HtmlArtifactPart"]
    assert [s.widget for s in manifest.side_panels] == ["html_artifact_pane"]
    assert manifest.icon == "code"
    # v1 is read-only: no owned tables, no router, no agent-creation config/uploads.
    assert manifest.tables == []
    assert manifest.router is None
    assert manifest.config_fields == []
    assert manifest.assets == []


def test_manifest_declares_react_only_execution_model():
    # CAPAB-02: carries a `wrap_model_call` prompt overlay `tools()` cannot
    # express, so it must declare itself incompatible with Graph agents rather
    # than silently contributing zero tools if one selects it.
    assert HtmlArtifactCapability.manifest.execution_models == ("react",)


def test_no_owned_migrations():
    # No tables -> the default (None) migrations location, unlike writable_document.
    assert HtmlArtifactCapability.migrations_location() is None
