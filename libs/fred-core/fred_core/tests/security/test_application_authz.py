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

"""Offline coverage for first-class application authorization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fred_core import AppPermission, Resource
from fred_core.security.rebac.application_authz import (
    APPLICATION_CAPABILITY_NAMESPACE_PREFIX,
    APPLICATION_CATALOG_NAMESPACE_PREFIX,
    app_ref,
    application_catalog_id,
    application_id_from_catalog_id,
    can_team_use_application,
    usable_application_ids,
)
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    _resource_for_permission,
)
from fred_core.tests.security.rebac_fakes import FakeRebacEngine

_SCHEMA_JSON = Path("fred_core/security/rebac/schema.fga.json")


def _type_definition(name: str) -> dict:
    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / _SCHEMA_JSON).read_text(encoding="utf-8"))
    matches = [item for item in schema["type_definitions"] if item["type"] == name]
    assert matches, f"generated schema.fga.json is missing the `{name}` type"
    return matches[0]


def _app_type() -> dict:
    return _type_definition("app")


def test_application_catalog_id_is_separate_from_openfga_reference() -> None:
    assert APPLICATION_CATALOG_NAMESPACE_PREFIX == "app__"
    assert APPLICATION_CAPABILITY_NAMESPACE_PREFIX == "app__"
    assert application_catalog_id("acme-forecast") == "app__acme-forecast"
    assert application_id_from_catalog_id("app__acme-forecast") == "acme-forecast"
    assert app_ref("acme-forecast") == RebacReference(
        type=Resource.APP, id="acme-forecast"
    )


@pytest.mark.parametrize("catalog_id", ["acme-forecast", "app__"])
def test_application_id_from_catalog_id_rejects_non_application_ids(
    catalog_id: str,
) -> None:
    with pytest.raises(ValueError):
        application_id_from_catalog_id(catalog_id)


def test_application_permissions_map_to_app_resource() -> None:
    assert Resource.APP.value == "app"
    assert _resource_for_permission(AppPermission.CAN_USE) is Resource.APP
    assert _resource_for_permission(AppPermission.CAN_MANAGE) is Resource.APP


@pytest.mark.asyncio
async def test_usable_application_ids_uses_raw_app_resources() -> None:
    rebac = FakeRebacEngine(resource_ids=["acme-forecast", "case-review"])

    result = await usable_application_ids(rebac, "team-1")

    assert result == {"acme-forecast", "case-review"}
    assert rebac.received_subject == RebacReference(type=Resource.TEAM, id="team-1")
    assert rebac.received_permission == AppPermission.CAN_USE
    assert rebac.received_resource_type == Resource.APP
    assert rebac.received_contextual_relations == [
        Relation(
            subject=RebacReference(type=Resource.TEAM, id="team-1"),
            relation=RelationType.TEAM,
            resource=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
        )
    ]


@pytest.mark.asyncio
async def test_usable_application_ids_preserves_disabled_rebac_signal() -> None:
    assert await usable_application_ids(NoopRebacEngine(), "team-1") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", ["personal", "personal-alice"])
async def test_usable_application_ids_rejects_personal_spaces(team_id: str) -> None:
    rebac = FakeRebacEngine(resource_ids=["acme-forecast"])

    assert await usable_application_ids(rebac, team_id) == set()
    assert rebac.received_subject is None


@pytest.mark.asyncio
async def test_can_team_use_application_checks_raw_app_reference() -> None:
    rebac = FakeRebacEngine(permitted=True)

    assert await can_team_use_application(rebac, "team-1", app_id="acme-forecast")
    assert rebac.checked == [
        (
            RebacReference(type=Resource.TEAM, id="team-1"),
            AppPermission.CAN_USE,
            RebacReference(type=Resource.APP, id="acme-forecast"),
        )
    ]
    assert [
        [relation.relation for relation in call]
        for call in rebac.checked_contextual_relations
    ] == [[RelationType.TEAM]]


@pytest.mark.asyncio
async def test_can_team_use_application_allows_when_rebac_is_disabled() -> None:
    assert await can_team_use_application(
        NoopRebacEngine(), "team-1", app_id="acme-forecast"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", ["personal", "personal-alice"])
async def test_can_team_use_application_rejects_personal_spaces(team_id: str) -> None:
    rebac = FakeRebacEngine(permitted=True)

    assert not await can_team_use_application(rebac, team_id, app_id="acme-forecast")
    assert rebac.checked == []


def test_schema_declares_only_collaborative_application_relations() -> None:
    relations = _app_type()["relations"]
    assert set(relations) == {
        "organization",
        "default_on",
        "enabled",
        "disabled",
        "can_manage",
        "inherited",
        "can_use",
    }
    metadata = _app_type()["metadata"]["relations"]
    for relation in ("organization", "default_on"):
        assert metadata[relation]["directly_related_user_types"] == [
            {"type": "organization"}
        ]
    for relation in ("enabled", "disabled"):
        assert metadata[relation]["directly_related_user_types"] == [{"type": "team"}]


def test_application_can_use_encodes_default_and_disabled_precedence() -> None:
    relations = _app_type()["relations"]
    inherited = relations["inherited"]["tupleToUserset"]
    assert inherited["tupleset"]["relation"] == "default_on"
    assert inherited["computedUserset"]["relation"] == "team"

    difference = relations["can_use"]["difference"]
    assert difference["base"]["union"]["child"] == [
        {"computedUserset": {"relation": "enabled"}},
        {"computedUserset": {"relation": "inherited"}},
    ]
    assert difference["subtract"]["computedUserset"]["relation"] == "disabled"


@pytest.mark.parametrize("type_name", ["app", "capability"])
def test_use_is_decided_by_team_grants_without_a_platform_wide_marker(
    type_name: str,
) -> None:
    """One absent marker tuple must not be able to deny every team at once.

    Applications and capabilities share this shape, so the invariant is
    asserted for both rather than for the type that happens to be under test.
    """
    relations = _type_definition(type_name)["relations"]

    assert "active" not in relations
    assert "active_teams" not in relations
    assert "intersection" not in relations["can_use"]
    assert "difference" in relations["can_use"]


def test_application_can_manage_follows_capability_governance() -> None:
    """App rows are toggled from the same admin page, behind the same org gate."""
    can_manage = _app_type()["relations"]["can_manage"]
    assert can_manage["tupleToUserset"]["tupleset"]["relation"] == "organization"
    assert (
        can_manage["tupleToUserset"]["computedUserset"]["relation"]
        == "can_manage_capabilities"
    )
    assert can_manage == _type_definition("capability")["relations"]["can_manage"]


@pytest.mark.asyncio
async def test_discovery_reads_applications_at_higher_consistency() -> None:
    """An eventually-consistent list can still show a just-revoked grant."""
    rebac = FakeRebacEngine(resource_ids=["acme-forecast"])

    await usable_application_ids(rebac, "team-1")

    assert rebac.lookup_resources_consistency_tokens == [RebacEngine.HIGHER_CONSISTENCY]


@pytest.mark.asyncio
async def test_team_application_check_reads_at_higher_consistency() -> None:
    """Admission must not be decided by a stale replica read."""
    rebac = FakeRebacEngine()

    await can_team_use_application(rebac, "team-1", app_id="acme-forecast")

    assert rebac.checked_consistency_tokens == [RebacEngine.HIGHER_CONSISTENCY]


@pytest.mark.asyncio
async def test_personal_spaces_are_refused_without_reading_applications() -> None:
    """The ceiling holds without a read, so no consistency choice applies."""
    rebac = FakeRebacEngine(resource_ids=["acme-forecast"])

    assert await usable_application_ids(rebac, "personal-alice") == set()
    assert not await can_team_use_application(
        rebac, "personal-alice", app_id="acme-forecast"
    )

    assert rebac.lookup_resources_consistency_tokens == []
    assert rebac.checked_consistency_tokens == []
