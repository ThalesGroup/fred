# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Static regression guards for the swift-clean starting state (AUTHZ-05/06).
Pure file I/O against the tracked Keycloak realm export templates and the
Swift OpenFGA model file - no running stack required (see tests/conftest.py).

These exist because the actual bug class here is invisible to `bash -n` or
`jq` validity checks: a syntactically valid realm-import JSON can still bake
in demo groups, group memberships, or group-admin Keycloak client roles that
silently reintroduce a Keycloak-groups-as-teams shape into the swift-clean
starting state. Each check below pins one specific claim from the AUTHZ-05/06
convergence pass so a future edit to these large, hand-maintained JSON files
cannot regress it unnoticed.

Historical note: this file used to also assert the (now removed) kea-legacy
OpenFGA model still carried the legacy `member`/`manager`/`owner` team
relations, as a comparative guard between the two authz modes. Kea-legacy
mode - and its model file - has been removed entirely from that repo (there
is only ever one mode now), so that comparative half is gone; what remains
is a standalone guard that the sole, current Swift model never regrows those
relations.

Cross-repo note (Part C relocation): this file moved here from
`fred-deployment-factory/validation/tests/` along with the rest of `validation/`,
but the files it guards (the realm-import templates, the OpenFGA model) still
live IN `fred-deployment-factory`, not in this `fred` checkout - unlike
`factory_config.py`'s fixture path, that ownership genuinely did not move.
REPO_ROOT below therefore still resolves cross-repo, to a sibling
`fred-deployment-factory` checkout (override via FRED_DEPLOYMENT_FACTORY_SRC).
This is a deliberate, narrow exception to "no more cross-repo path assumptions"
for validation/ - flagged for the developer, not silently papered over.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(
    os.getenv(
        "FRED_DEPLOYMENT_FACTORY_SRC",
        str(Path(__file__).resolve().parents[3] / "fred-deployment-factory"),
    )
)

if not REPO_ROOT.is_dir():
    pytest.skip(
        f"fred-deployment-factory checkout not found at {REPO_ROOT!s} - these guards check "
        "realm-import/OpenFGA-model files owned by that repo, not this one. Set "
        "FRED_DEPLOYMENT_FACTORY_SRC to your checkout's path if it isn't a sibling of this "
        "`fred` checkout.",
        allow_module_level=True,
    )

SWIFT_REALM_TEMPLATES = [
    REPO_ROOT / "docker/keycloak/app-realm.json.template",
    REPO_ROOT / "k3d/files/keycloak/app-realm.json.template",
]

# A Swift team is never a Keycloak group in the realm-import's starting
# state. These templates must never bake in a demo group, a per-user group
# membership, or a default groups-scope - not because they are "the Swift
# template" (there is now only one), but because post-install, not the
# import, is the sole owner of any authz-related state.
GROUP_SCOPED_SERVICE_ACCOUNTS = (
    "service-account-agentic",
    "service-account-knowledge-flow",
    "service-account-control-plane",
)


def _load(path: Path) -> dict:
    assert path.is_file(), f"{path} not found"
    return json.loads(path.read_text())


@pytest.mark.parametrize("template_path", SWIFT_REALM_TEMPLATES, ids=lambda p: p.name)
def test_realm_template_has_no_demo_groups(template_path: Path) -> None:
    """The realm-import template defines zero groups."""
    realm = _load(template_path)
    assert realm.get("groups", []) == [], (
        f"{template_path} bakes in group(s) {realm.get('groups')!r} - a Swift team is never a "
        f"Keycloak group"
    )


@pytest.mark.parametrize("template_path", SWIFT_REALM_TEMPLATES, ids=lambda p: p.name)
def test_realm_template_users_have_no_group_membership(template_path: Path) -> None:
    """No user in the realm-import template belongs to any group."""
    realm = _load(template_path)
    offenders = {
        u.get("username"): u.get("groups")
        for u in realm.get("users", [])
        if u.get("groups")
    }
    assert not offenders, f"{template_path}: users with non-empty groups: {offenders!r}"


@pytest.mark.parametrize("template_path", SWIFT_REALM_TEMPLATES, ids=lambda p: p.name)
def test_realm_template_app_client_has_no_default_groups_scope(template_path: Path) -> None:
    """The 'app' client does not default to groups-scope at import time."""
    realm = _load(template_path)
    app_clients = [c for c in realm.get("clients", []) if c.get("clientId") == "app"]
    assert len(app_clients) == 1, f"{template_path}: expected exactly one 'app' client, found {len(app_clients)}"
    default_scopes = app_clients[0].get("defaultClientScopes", [])
    assert "groups-scope" not in default_scopes, (
        f"{template_path}: 'app' client defaults to groups-scope - nothing should ever attach "
        f"it, least of all the import itself"
    )


@pytest.mark.parametrize("template_path", SWIFT_REALM_TEMPLATES, ids=lambda p: p.name)
def test_realm_template_service_accounts_have_no_group_admin_roles(template_path: Path) -> None:
    """No FRED service account is baked in with a Keycloak group-admin role.

    No app in the fred product (agentic/knowledge-flow/control-plane) calls
    a Keycloak group-admin API - confirmed against fred's source during the
    AUTHZ-05/06 pass. query-groups/view-groups/account:view-groups are
    therefore never a legitimate grant for these service accounts.
    """
    realm = _load(template_path)
    offenders: dict[str, list[str]] = {}
    for user in realm.get("users", []):
        username = user.get("username")
        if username not in GROUP_SCOPED_SERVICE_ACCOUNTS:
            continue
        client_roles = user.get("clientRoles", {})
        bad_roles = [
            r for r in client_roles.get("realm-management", []) if r in ("query-groups", "view-groups")
        ] + [r for r in client_roles.get("account", []) if r == "view-groups"]
        if bad_roles:
            offenders[username] = bad_roles
    assert not offenders, f"{template_path}: service accounts with group-admin roles baked in: {offenders!r}"


SWIFT_MODEL_PATHS = [
    REPO_ROOT / "docker/openfga/openfga-model.json",
    REPO_ROOT / "k3d/files/openfga/openfga-model.json",
]


@pytest.mark.parametrize("model_path", SWIFT_MODEL_PATHS, ids=lambda p: p.name)
def test_swift_model_has_no_legacy_team_vocabulary(model_path: Path) -> None:
    """The Swift OpenFGA model never carries the legacy member/manager/owner team relations."""
    model = _load(model_path)
    team_type = next((t for t in model.get("type_definitions", []) if t.get("type") == "team"), None)
    assert team_type is not None, f"{model_path}: no 'team' type definition"
    relations = set(team_type.get("relations", {}).keys())
    leaked = relations & {"member", "manager", "owner"}
    assert not leaked, (
        f"{model_path}: Swift model carries legacy team relations {leaked!r} - "
        f"the current model must stay {{team_admin, team_editor, team_analyst, team_member}}-shaped"
    )
