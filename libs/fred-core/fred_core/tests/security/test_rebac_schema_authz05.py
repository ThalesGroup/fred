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

"""Guard the AUTHZ-05 escalation fix directly on the compiled OpenFGA model.

`team.owner` used to be `[user] or admin from organization`: any Keycloak
`admin` app-role holder was silently an implicit owner of every team (RFC
FRED-AUTHORIZATION-TARGET-MODEL-RFC.md §24.2). This test reads the same
compiled `schema.fga.json` the running engine loads, so a future schema.fga
edit that reintroduces the escalation (or forgets to regenerate the JSON)
fails offline instead of only surfacing in a live OpenFGA integration run.

Second pass (RFC §26/§27/§28): team roles renamed `owner`/`manager`/`member`
-> `team_admin`/`team_editor`/`team_member`, plus a new `team_analyst` role.
"""

from __future__ import annotations

import json

from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA


def _type_definition(type_name: str) -> dict:
    model = json.loads(DEFAULT_SCHEMA)
    return next(t for t in model["type_definitions"] if t["type"] == type_name)


def test_team_admin_is_not_derived_from_organization_admin() -> None:
    team = _type_definition("team")
    team_admin_definition = team["relations"]["team_admin"]

    assert team_admin_definition == {"this": {}}, (
        "team.team_admin must only be a directly-assigned relation. A "
        "'tupleToUserset'/'computedUserset' referencing 'organization' or "
        "'admin'/'platform_admin' here would resurrect the "
        "platform-admin-sees-every-team bug."
    )


def test_organization_has_target_platform_roles() -> None:
    organization = _type_definition("organization")

    assert "platform_admin" in organization["relations"]
    assert "platform_observer" in organization["relations"]


def test_schema_contains_all_six_target_roles() -> None:
    """The full AUTHZ-05 target vocabulary must exist, exactly as named."""
    organization = _type_definition("organization")
    team = _type_definition("team")

    assert "platform_admin" in organization["relations"]
    assert "platform_observer" in organization["relations"]
    assert "team_admin" in team["relations"]
    assert "team_editor" in team["relations"]
    assert "team_analyst" in team["relations"]
    assert "team_member" in team["relations"]

    # No legacy relation names must survive on the team type.
    for legacy in ("owner", "manager", "member"):
        assert legacy not in team["relations"], (
            f"team.{legacy} is a legacy relation name and must not appear in "
            f"the target schema (AUTHZ-05 §26)."
        )


def test_team_role_administration_has_no_platform_escalation() -> None:
    """No relation (`platform_admin` or otherwise) may grant team role
    administration - `can_administer_admins`/`can_administer_editors`/
    `can_administer_analysts`/`can_administer_members` must be
    team_admin-only.

    A `platform_admin from organization` exception was tried here for team
    bootstrap (RFC #1957 review) and reverted: OpenFGA relations are
    stateless, so "grant this only if the team has no admin yet" cannot be
    expressed - the grant applied unconditionally, on every team, forever.
    Combined with control-plane's add_team_member/update_team_member (which
    check exactly this capability), that let a platform_admin self-promote to
    admin/editor of any existing team and inherit full team data access
    through team_admin/team_editor/team_analyst -> team_member: the exact
    escalation this RFC exists to close, reintroduced through a different
    door. See RFC §24.7. Team bootstrap is instead a one-shot, dedicated
    action outside this schema (RFC §28).
    """
    team = _type_definition("team")

    for capability in (
        "can_administer_admins",
        "can_administer_editors",
        "can_administer_analysts",
        "can_administer_members",
        "can_update_info",
    ):
        assert team["relations"][capability] == {
            "computedUserset": {"relation": "team_admin"}
        }, (
            f"{capability} must be team_admin-only - no platform_admin (or "
            f"any other) escalation into team role administration."
        )


def test_can_create_team_is_platform_admin_only() -> None:
    """`can_create_team` (the bootstrap gate, RFC §28) is `platform_admin`-only
    (AUTHZ-05 review item 5): the legacy `admin` bridge had no other caller in
    the repo than `create_team`, so it is cut rather than perpetuated. This
    must not be confused with a team relation: `platform_admin` still does not
    appear anywhere in the `team` type's relation definitions (checked above),
    so this capability can only ever gate the one-shot create-team action,
    never ongoing team access."""
    organization = _type_definition("organization")
    can_create_team = organization["relations"]["can_create_team"]

    assert can_create_team == {"computedUserset": {"relation": "platform_admin"}}


def test_can_use_team_agents_is_team_member_only() -> None:
    """AUTHZ-05 review item 1b: seeing/using a team's agents (templates and
    managed instances) must be gated on `team_member`, never on `can_read`
    (which also admits `public`) - otherwise any visitor of a public team
    could enumerate that team's agents."""
    team = _type_definition("team")

    assert team["relations"]["can_use_team_agents"] == {
        "computedUserset": {"relation": "team_member"}
    }


def test_can_observe_platform_gates_both_kpi_dashboards() -> None:
    """AUTHZ-05 review item 16: `can_observe_platform` is the one relation for
    cross-user / platform-wide KPI observation, gating both the standalone KPI
    dashboard (`/monitoring/kpis`) and the control-plane Analytics presets
    (`/admin/analytics`). It is gated on `platform_observer` directly - which
    already unions in `platform_admin` - so both roles pass. The previous,
    separate `can_read_kpi_global` (platform_admin-only) was a duplicate the
    RFC never asked for (§6.1 defines only `can_observe_platform`) and is
    retired: it must not reappear in the schema."""
    organization = _type_definition("organization")

    assert organization["relations"]["can_observe_platform"] == {
        "computedUserset": {"relation": "platform_observer"}
    }
    assert "can_read_kpi_global" not in organization["relations"]


def test_no_legacy_organization_role_relations_survive() -> None:
    """AUTHZ-05 review item 8a: the Keycloak `admin`/`editor`/`viewer` bridge
    is removed outright, not kept under a legacy_bridge toggle - platform
    roles are `platform_admin`/`platform_observer` stored tuples only."""
    organization = _type_definition("organization")

    for legacy in ("admin", "editor", "viewer"):
        assert legacy not in organization["relations"], (
            f"organization.{legacy} is the removed Keycloak-role bridge and "
            f"must not reappear in the target schema (AUTHZ-05 §29-32)."
        )


def test_team_registry_governance_capabilities_are_platform_admin_only() -> None:
    """AUTHZ-05 review item 9 (RFC Part 6 §32): `can_list_all_teams`,
    `can_delete_team`, `can_rescue_team_admin` govern the team *registry*
    (existence), never a team's data - `platform_admin`-only, like
    `can_create_team` above. None of the three may ever be redefined to also
    accept a team relation: that would let `platform_admin` reach team data
    through the registry surface, the exact escalation this RFC closes."""
    organization = _type_definition("organization")

    for capability in (
        "can_list_all_teams",
        "can_delete_team",
        "can_rescue_team_admin",
    ):
        assert organization["relations"][capability] == {
            "computedUserset": {"relation": "platform_admin"}
        }, f"{capability} must be platform_admin-only."
