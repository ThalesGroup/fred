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
"""

from __future__ import annotations

import json

from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA


def _type_definition(type_name: str) -> dict:
    model = json.loads(DEFAULT_SCHEMA)
    return next(t for t in model["type_definitions"] if t["type"] == type_name)


def test_team_owner_is_not_derived_from_organization_admin() -> None:
    team = _type_definition("team")
    owner_definition = team["relations"]["owner"]

    assert owner_definition == {"this": {}}, (
        "team.owner must only be a directly-assigned relation. A "
        "'tupleToUserset'/'computedUserset' referencing 'organization' or "
        "'admin' here would resurrect the platform-admin-sees-every-team bug."
    )


def test_organization_has_target_platform_roles() -> None:
    organization = _type_definition("organization")

    assert "platform_admin" in organization["relations"]
    assert "platform_observer" in organization["relations"]


def test_team_role_administration_has_no_platform_escalation() -> None:
    """No relation (`platform_admin` or otherwise) may grant team role
    administration - `can_administer_owners`/`can_administer_managers` must be
    owner-only.

    A `platform_admin from organization` exception was tried here for team
    bootstrap (RFC #1957 review) and reverted: OpenFGA relations are
    stateless, so "grant this only if the team has no owner yet" cannot be
    expressed - the grant applied unconditionally, on every team, forever.
    Combined with control-plane's add_team_member/update_team_member (which
    check exactly this capability), that let a platform_admin self-promote to
    owner/manager of any existing team and inherit full team data access
    through owner -> manager -> member: the exact escalation this RFC exists
    to close, reintroduced through a different door. See RFC §24.7.
    """
    team = _type_definition("team")

    for capability in (
        "can_administer_owners",
        "can_administer_managers",
        "can_administer_members",
        "can_update_info",
    ):
        assert team["relations"][capability] == {
            "computedUserset": {"relation": "owner"}
        }, (
            f"{capability} must be owner-only - no platform_admin (or any other) "
            f"escalation into team role administration."
        )
