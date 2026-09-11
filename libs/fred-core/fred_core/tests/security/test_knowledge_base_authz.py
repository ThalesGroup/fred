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

"""Offline coverage for Knowledge Base definition authorization."""

from __future__ import annotations

import json
from pathlib import Path


from fred_core import Resource
from fred_core.security.rebac.knowledge_base_authz import (
    knowledge_base_definition_ref,
)
from fred_core.security.rebac.rebac_engine import (
    KnowledgeBaseDefinitionPermission,
    RebacReference,
    _resource_for_permission,
)

_SCHEMA_JSON = Path("fred_core/security/rebac/schema.fga.json")
_TYPE_NAME = "knowledge_base_definition"


def _type_definition(name: str) -> dict:
    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / _SCHEMA_JSON).read_text(encoding="utf-8"))
    matches = [item for item in schema["type_definitions"] if item["type"] == name]
    assert matches, f"generated schema.fga.json is missing the `{name}` type"
    return matches[0]


def _definition_type() -> dict:
    return _type_definition(_TYPE_NAME)


# --------------------------------------------------------------------------
# Permission -> resource mapping
# --------------------------------------------------------------------------


def test_knowledge_base_permissions_map_to_their_own_resource() -> None:
    assert Resource.KNOWLEDGE_BASE_DEFINITION.value == _TYPE_NAME
    assert (
        _resource_for_permission(KnowledgeBaseDefinitionPermission.CAN_USE)
        is Resource.KNOWLEDGE_BASE_DEFINITION
    )
    assert (
        _resource_for_permission(KnowledgeBaseDefinitionPermission.CAN_MANAGE)
        is Resource.KNOWLEDGE_BASE_DEFINITION
    )


def test_definition_reference_is_neither_capability_nor_app() -> None:
    ref = knowledge_base_definition_ref("local-folder")
    assert ref == RebacReference(
        type=Resource.KNOWLEDGE_BASE_DEFINITION, id="local-folder"
    )
    assert ref.type is not Resource.CAPABILITY
    assert ref.type is not Resource.APP


# --------------------------------------------------------------------------
# The compiled schema
# --------------------------------------------------------------------------


def test_schema_declares_the_knowledge_base_definition_type() -> None:
    relations = _definition_type()["relations"]
    assert set(relations) == {
        "organization",
        "default_on",
        "enabled",
        "disabled",
        "can_manage",
        "inherited",
        "can_use",
    }
    metadata = _definition_type()["metadata"]["relations"]
    for relation in ("organization", "default_on"):
        assert metadata[relation]["directly_related_user_types"] == [
            {"type": "organization"}
        ]
    for relation in ("enabled", "disabled"):
        assert metadata[relation]["directly_related_user_types"] == [{"type": "team"}]


def test_definition_can_use_encodes_default_and_disabled_precedence() -> None:
    relations = _definition_type()["relations"]
    inherited = relations["inherited"]["tupleToUserset"]
    assert inherited["tupleset"]["relation"] == "default_on"
    assert inherited["computedUserset"]["relation"] == "team"

    difference = relations["can_use"]["difference"]
    assert difference["base"]["union"]["child"] == [
        {"computedUserset": {"relation": "enabled"}},
        {"computedUserset": {"relation": "inherited"}},
    ]
    assert difference["subtract"]["computedUserset"]["relation"] == "disabled"


def test_definition_use_is_decided_by_team_grants_without_a_platform_marker() -> None:
    """One absent marker tuple must not be able to deny every team at once."""

    relations = _definition_type()["relations"]

    assert "active" not in relations
    assert "active_teams" not in relations
    assert "intersection" not in relations["can_use"]
    assert "difference" in relations["can_use"]


def test_definition_can_manage_is_platform_admin() -> None:
    can_manage = _definition_type()["relations"]["can_manage"]["tupleToUserset"]
    assert can_manage["tupleset"]["relation"] == "organization"
    assert can_manage["computedUserset"]["relation"] == "platform_admin"
