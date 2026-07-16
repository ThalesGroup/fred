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
Offline coverage for the `capability` OpenFGA type (CAPAB-01 / #1980, RFC §8.1).

The tri-state `can_use` semantics themselves are exercised against a live
OpenFGA in `tests/integration/test_rebac.py`; these tests assert the pieces that
must hold WITHOUT a server: the generated schema carries the type and its
computed permissions, and the Python permission enum maps to the right resource.
"""

from __future__ import annotations

import json
from pathlib import Path

from fred_core import CapabilityPermission, Resource
from fred_core.security.rebac.rebac_engine import (
    RelationType,
    _resource_for_permission,
)

_SCHEMA_JSON = Path("fred_core/security/rebac/schema.fga.json")


def _load_schema() -> dict:
    # Resolve relative to this test file so it works from any cwd.
    here = Path(__file__).resolve()
    root = here.parents[3]  # .../libs/fred-core
    return json.loads((root / _SCHEMA_JSON).read_text(encoding="utf-8"))


def _capability_type() -> dict:
    schema = _load_schema()
    caps = [t for t in schema["type_definitions"] if t["type"] == "capability"]
    assert caps, "generated schema.fga.json is missing the `capability` type"
    return caps[0]


def test_capability_resource_value() -> None:
    assert Resource.CAPABILITY.value == "capability"


def test_capability_permissions_map_to_capability_resource() -> None:
    assert _resource_for_permission(CapabilityPermission.CAN_USE) is Resource.CAPABILITY
    assert (
        _resource_for_permission(CapabilityPermission.CAN_MANAGE) is Resource.CAPABILITY
    )


def test_capability_structural_relation_types_exist() -> None:
    # The enablement API writes these tuple relations.
    assert RelationType.ENABLED.value == "enabled"
    assert RelationType.DISABLED.value == "disabled"
    assert RelationType.DEFAULT_ON.value == "default_on"
    # Personal-space class positions (CAPAB-01 / #1961, RFC §8.4).
    assert RelationType.PERSONAL_ON.value == "personal_on"
    assert RelationType.PERSONAL_DISABLED.value == "personal_disabled"
    assert RelationType.PERSONAL_TEAM.value == "personal_team"


def test_schema_declares_capability_relations() -> None:
    cap = _capability_type()
    relations = cap["relations"]
    for name in (
        "organization",
        "default_on",
        "enabled",
        "disabled",
        "personal_on",
        "personal_disabled",
        "personal_grant",
        "personal_block",
        "inherited",
    ):
        assert name in relations, f"structural relation {name!r} missing"
    # Callers only ever check these two computed permissions.
    assert "can_use" in relations
    assert "can_manage" in relations


def test_can_use_encodes_the_tristate() -> None:
    # TEAM-SUBJECT shape: (enabled OR inherited) BUT NOT disabled. The subject of
    # a `can_use` check is the team the agent belongs to — a user-subject shape
    # (`member from enabled`) would leak a capability enabled for one of the
    # user's teams into every team context they browse.
    cap = _capability_type()
    can_use = cap["relations"]["can_use"]
    difference = can_use["difference"]
    base = difference["base"]["union"]["child"]
    assert {"computedUserset": {"relation": "enabled"}} in base
    assert {"computedUserset": {"relation": "inherited"}} in base
    assert difference["subtract"]["computedUserset"]["relation"] == "disabled"


def test_inherited_encodes_default_on_and_personal_class() -> None:
    # `inherited` = (team from default_on OR personal_grant) BUT NOT
    # personal_block — the intermediate layer the personal-class opt-out
    # subtracts from, so it never touches a per-space explicit grant
    # (CAPAB-01 / #1961, RFC §8.4).
    cap = _capability_type()
    inherited = cap["relations"]["inherited"]
    difference = inherited["difference"]
    base = difference["base"]["union"]["child"]
    default_on = next(c["tupleToUserset"] for c in base if "tupleToUserset" in c)
    assert default_on["tupleset"]["relation"] == "default_on"
    # Resolved through the organization's `team` reverse edge (supplied as a
    # contextual tuple at check time — never persisted).
    assert default_on["computedUserset"]["relation"] == "team"
    assert {"computedUserset": {"relation": "personal_grant"}} in base
    assert difference["subtract"]["computedUserset"]["relation"] == "personal_block"

    # The personal-class relations resolve through the org's personal_team edge.
    personal_grant = cap["relations"]["personal_grant"]["tupleToUserset"]
    assert personal_grant["tupleset"]["relation"] == "personal_on"
    assert personal_grant["computedUserset"]["relation"] == "personal_team"
    personal_block = cap["relations"]["personal_block"]["tupleToUserset"]
    assert personal_block["tupleset"]["relation"] == "personal_disabled"
    assert personal_block["computedUserset"]["relation"] == "personal_team"


def test_organization_declares_team_reverse_edges() -> None:
    # The contextual reverse indexes `organization#team@team:<id>` and
    # `organization#personal_team@team:<id>` used by team-subject capability
    # checks must stay declared on the organization.
    schema = _load_schema()
    org = next(t for t in schema["type_definitions"] if t["type"] == "organization")
    relations = org["metadata"]["relations"]
    assert relations["team"]["directly_related_user_types"] == [{"type": "team"}]
    assert relations["personal_team"]["directly_related_user_types"] == [
        {"type": "team"}
    ]


def test_can_manage_is_platform_admin() -> None:
    cap = _capability_type()
    can_manage = cap["relations"]["can_manage"]
    ttu = can_manage["tupleToUserset"]
    assert ttu["tupleset"]["relation"] == "organization"
    assert ttu["computedUserset"]["relation"] == "platform_admin"
