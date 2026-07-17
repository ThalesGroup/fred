# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Unit tests for `factory_config.FactoryUser` (role resolution) and
`factory_config.load_users` (YAML -> typed matrix), covering the cases
AUTHZ-06's cumulative-role rework needs locked in against regression:
a simple single role, a cumulative multi-role grant, the legacy
`teams[]` -> `team_member` fallback, the admin/editor/analyst distinction,
and a neutral identity with no role at all.

No running stack required - see tests/conftest.py.
"""

from __future__ import annotations

from factory_config import USERS, FactoryUser, load_users


def _user(**overrides) -> FactoryUser:
    defaults = dict(
        username="test-user",
        app_roles=(),
        teams=(),
        team_roles={},
        platform_roles=(),
    )
    defaults.update(overrides)
    return FactoryUser(**defaults)


# --- simple (single) role ----------------------------------------------------


def test_simple_team_editor_role_is_reported_and_isolated():
    user = _user(teams=("fredlab",), team_roles={"fredlab": frozenset({"team_editor"})})

    assert user.relations_in("fredlab") == frozenset({"team_editor"})
    assert user.is_team_editor_in("fredlab") is True
    assert user.is_team_admin_in("fredlab") is False
    assert user.can_enroll_in("fredlab") is True  # editor can enroll agents


def test_simple_role_does_not_leak_to_another_team():
    user = _user(teams=("fredlab",), team_roles={"fredlab": frozenset({"team_admin"})})

    assert user.relations_in("northbridge") == frozenset()
    assert user.is_team_admin_in("northbridge") is False
    assert user.can_enroll_in("northbridge") is False


# --- cumulative role (AUTHZ-06) ----------------------------------------------


def test_cumulative_role_holds_all_three_relations_at_once():
    user = _user(
        teams=("fredlab",),
        team_roles={"fredlab": frozenset({"team_admin", "team_editor", "team_analyst"})},
    )

    relations = user.relations_in("fredlab")
    assert relations == frozenset({"team_admin", "team_editor", "team_analyst"})
    assert user.is_team_admin_in("fredlab") is True
    assert user.is_team_editor_in("fredlab") is True
    assert user.can_enroll_in("fredlab") is True


def test_cumulative_role_is_independent_per_team():
    # team_admin on fredlab only, team_editor on northbridge only - not both on both.
    user = _user(
        teams=("fredlab", "northbridge"),
        team_roles={
            "fredlab": frozenset({"team_admin"}),
            "northbridge": frozenset({"team_editor"}),
        },
    )

    assert user.is_team_admin_in("fredlab") is True
    assert user.is_team_editor_in("fredlab") is False
    assert user.is_team_admin_in("northbridge") is False
    assert user.is_team_editor_in("northbridge") is True


# --- legacy teams[] -> team_member fallback ----------------------------------


def test_teams_list_membership_without_explicit_role_falls_back_to_team_member():
    user = _user(teams=("fredlab",), team_roles={})

    assert user.relations_in("fredlab") == frozenset({"team_member"})
    assert user.is_team_admin_in("fredlab") is False
    assert user.is_team_editor_in("fredlab") is False
    assert user.can_enroll_in("fredlab") is False  # plain member cannot enroll


def test_explicit_team_roles_take_precedence_over_the_team_member_fallback():
    # 'fredlab' is in teams[] (would fall back to team_member alone) but also has
    # an explicit team_roles entry - the explicit relation set wins, no implicit
    # team_member is added on top of it.
    user = _user(teams=("fredlab",), team_roles={"fredlab": frozenset({"team_editor"})})

    assert user.relations_in("fredlab") == frozenset({"team_editor"})


# --- admin/editor/analyst distinction ----------------------------------------


def test_team_analyst_alone_is_neither_admin_nor_editor_and_cannot_enroll():
    user = _user(teams=("fredlab",), team_roles={"fredlab": frozenset({"team_analyst"})})

    assert user.is_team_admin_in("fredlab") is False
    assert user.is_team_editor_in("fredlab") is False
    assert user.can_enroll_in("fredlab") is False


def test_legacy_owner_and_manager_map_to_the_same_admin_editor_predicates():
    # Kea rehearsal vocabulary (owner/manager) must satisfy the same
    # is_team_admin_in/is_team_editor_in predicates as the Swift target
    # vocabulary (team_admin/team_editor) - conftest.py's bootstrap and the
    # scenario files branch on these predicates, not on the raw relation name.
    owner = _user(teams=("fredlab",), team_roles={"fredlab": frozenset({"owner"})})
    manager = _user(teams=("fredlab",), team_roles={"fredlab": frozenset({"manager"})})

    assert owner.is_team_admin_in("fredlab") is True
    assert owner.can_enroll_in("fredlab") is True
    assert manager.is_team_editor_in("fredlab") is True
    assert manager.can_enroll_in("fredlab") is True


# --- neutral identity: no role at all ----------------------------------------


def test_neutral_identity_has_no_team_role_and_no_platform_role():
    user = _user()

    assert user.relations_in("fredlab") == frozenset()
    assert user.is_team_admin_in("fredlab") is False
    assert user.is_team_editor_in("fredlab") is False
    assert user.can_enroll_in("fredlab") is False
    assert user.is_platform_admin is False
    assert user.is_platform_observer is False
    assert user.is_global_admin is False


# --- platform roles (AUTHZ-05, independent of team_roles) -------------------


def test_platform_admin_and_observer_are_independent_of_team_roles():
    admin = _user(platform_roles=("admin",))
    observer = _user(platform_roles=("observer",))

    assert admin.is_platform_admin is True
    assert admin.is_platform_observer is False
    assert observer.is_platform_admin is False
    assert observer.is_platform_observer is True
    # A platform role grants no implicit team relation (AUTHZ-05 §24.2).
    assert admin.relations_in("fredlab") == frozenset()


# --- load_users() against the real config/configuration.yaml -----------------


def test_load_users_parses_the_real_config_without_error():
    users = load_users()
    assert users, "config/configuration.yaml produced no users"
    assert all(isinstance(u, FactoryUser) for u in users.values())


def test_load_users_matches_the_module_level_users_singleton():
    # USERS is load_users() called once at import time - re-calling it must be
    # idempotent and produce an equivalent matrix (guards against hidden state).
    assert load_users() == USERS


def test_load_users_gives_priya_the_documented_cumulative_fredlab_roles():
    # Locks in the AUTHZ-06 cumulative-roles fixture (validation/README.md,
    # config/configuration.yaml) that test_cumulative_team_roles.py depends on.
    priya = USERS.get("priya")
    assert priya is not None, "config/configuration.yaml must define 'priya'"
    assert priya.relations_in("fredlab") == frozenset({"team_admin", "team_editor", "team_analyst"})


def test_load_users_gives_marc_bob_elena_a_single_isolated_fredlab_role_each():
    marc, bob, elena = USERS.get("marc"), USERS.get("bob"), USERS.get("elena")
    assert marc is not None and bob is not None and elena is not None, (
        "config/configuration.yaml must define 'marc', 'bob', and 'elena'"
    )
    assert marc.relations_in("fredlab") == frozenset({"team_admin"})
    assert bob.is_team_editor_in("fredlab") is True
    assert bob.is_team_admin_in("fredlab") is False
    assert elena.relations_in("fredlab") == frozenset({"team_analyst"})
