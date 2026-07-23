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

"""Registry boot invariants for the writable_document capability (RFC §4, §7.1).

Registering the capability into a fresh `CapabilityRegistry` and calling
`.validate()` must be green: the owned table is prefixed `cap_writable_document_`
with no foreign keys, and the `writable_document` chat-part kind is unique.
"""

from __future__ import annotations

from fred_capability_writable_document.capability import WritableDocumentCapability
from fred_runtime.capabilities.registry import CapabilityRegistry


def test_capability_registers_and_validates_clean():
    registry = CapabilityRegistry()
    registry.register(WritableDocumentCapability())
    # No raise = all boot invariants hold (table hygiene, chat-part kind, env, scope).
    registry.validate()
    assert "writable_document" in registry.ids()


def test_owned_table_is_prefixed_and_has_no_foreign_keys():
    manifest = WritableDocumentCapability.manifest
    assert [t.__tablename__ for t in manifest.tables] == ["cap_writable_document_docs"]
    table = manifest.tables[0].__table__
    assert table.name.startswith("cap_writable_document_")
    assert not table.foreign_keys


def test_manifest_declares_chat_part_side_panel_and_router():
    manifest = WritableDocumentCapability.manifest
    assert [p.__name__ for p in manifest.chat_parts] == ["WritableDocumentPart"]
    assert [s.widget for s in manifest.side_panels] == ["writable_document_pane"]
    assert manifest.router is not None
    # No agent-creation config, no upload slots (config-less capability).
    assert manifest.config_fields == []
    assert manifest.assets == []
