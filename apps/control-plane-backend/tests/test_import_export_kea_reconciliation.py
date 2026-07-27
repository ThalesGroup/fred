"""KEA CUTOVER 2026 — coverage for `kea_reconciliation.py`'s specific behaviour:
username-based identity resolution (matched / relinked / pending), plain
team-membership restored from Keycloak group data, and the admin-less-team
warning. Delete this file together with `kea_reconciliation.py` after cutover.

Reuses `test_import_export_kea_bundle.py`'s bundle/engine helpers rather than
duplicating them — same underlying `run_import` integration, different angle.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from control_plane_backend.import_export.kea_reconciliation import (
    KeaReconciliationReport,
    KeaUserResolver,
    drop_orphan_team_relations,
    format_usernames_for_warning,
    kea_known_group_ids,
    kea_username_by_sub,
    resolve_user_sub,
)
from control_plane_backend.users.dependencies import UserServiceDependencies
from fred_core import RebacReference, Relation, RelationType, Resource
from tests.test_import_export_kea_bundle import (
    UID_BOB,
    UID_LIAM,
    FakeRebac,
    _import,
    _kea_bundle,
    _make_engine,
    _rel_key,
)

UID_UNKNOWN = "b3f6a1e2-2222-4444-8888-000000000001"

# `find_user_subs_bulk`/`find_user_sub_by_username` are monkeypatched in every
# test that uses this, so the real shape of `UserServiceDependencies` never
# matters — only that `create()` sees a non-`None` value and calls the
# monkeypatched bulk sweep instead of short-circuiting to `{}`.
_FAKE_USER_DEPS = cast(UserServiceDependencies, object())

# KEA CUTOVER 2026 — pytest fixtures are NOT inherited across sibling test
# modules just by importing helpers from them, so this file needs its own copy
# of the "Plan A" bulk-snapshot stub (see test_import_export_kea_bundle.py for
# the rationale). Individual tests below override it locally where they need a
# different outcome (PENDING / RELINKED) — the bulk snapshot is authoritative,
# so overriding it is the only way to change what a test's users resolve to.
_PLAN_A_USERNAME_TO_SUB = {"bob": UID_BOB, "liam": UID_LIAM}


@pytest.fixture(autouse=True)
def _stub_username_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_find_user_subs_bulk(_deps: object) -> dict[str, str]:
        return dict(_PLAN_A_USERNAME_TO_SUB)

    monkeypatch.setattr(
        "control_plane_backend.import_export.kea_reconciliation.find_user_subs_bulk",
        _fake_find_user_subs_bulk,
    )


def test_kea_username_by_sub_and_known_group_ids() -> None:
    realm = {
        "groups": [{"id": "g1", "name": "northbridge"}, {"id": "g2"}],
        "users": [{"id": UID_BOB, "username": "bob"}, {"id": "no-username"}],
    }
    assert kea_username_by_sub(realm) == {UID_BOB: "bob"}
    assert kea_known_group_ids(realm) == {"g1", "g2"}


def test_format_usernames_for_warning_caps_a_large_list() -> None:
    """Caught a real crash: an uncapped join of 1008 usernames in a `pg_notify`
    payload exceeds Postgres's ~8000-byte NOTIFY limit and fails the whole
    import task even though every write already committed (2026-07-25)."""
    names = [f"user{i}" for i in range(1500)]
    rendered = format_usernames_for_warning(names)
    # 20 shown names (19 separators) + 1 more before the "… (+N more)" suffix.
    assert rendered.count(",") == 20
    assert rendered.endswith("(+1480 more)")
    assert len(rendered) < 500


def test_format_usernames_for_warning_no_truncation_under_the_cap() -> None:
    assert format_usernames_for_warning(["bob", "alice"]) == "alice, bob"


def test_drop_orphan_team_relations_filters_both_subject_and_resource() -> None:
    """`drop_orphan_teams` excludes an orphan team from `teammetadata` — this is
    the companion filter for the OpenFGA tuple-restore path (a separate list, not
    filtered by `drop_orphan_teams` itself; see its call site in importer.py)."""
    kept = Relation(
        subject=RebacReference(Resource.USER, "u1"),
        relation=RelationType.TEAM_ADMIN,
        resource=RebacReference(Resource.TEAM, "kept-team"),
    )
    dropped_as_resource = Relation(
        subject=RebacReference(Resource.ORGANIZATION, "fred"),
        relation=RelationType.ORGANIZATION,
        resource=RebacReference(Resource.TEAM, "orphan-team"),
    )
    dropped_as_subject = Relation(
        subject=RebacReference(Resource.TEAM, "orphan-team"),
        relation=RelationType.TEAM_MEMBER,
        resource=RebacReference(Resource.RESOURCES, "r1"),
    )
    result = drop_orphan_team_relations(
        [kept, dropped_as_resource, dropped_as_subject], ["orphan-team"]
    )
    assert result == [kept]


def test_drop_orphan_team_relations_no_op_when_nothing_dropped() -> None:
    kept = Relation(
        subject=RebacReference(Resource.USER, "u1"),
        relation=RelationType.TEAM_ADMIN,
        resource=RebacReference(Resource.TEAM, "team-1"),
    )
    assert drop_orphan_team_relations([kept], []) == [kept]


@pytest.mark.asyncio
async def test_unresolvable_user_is_pending_not_failed(tmp_path: Path) -> None:
    """A kea sub with no matching swift Keycloak user (per the stub's resolution
    table) is dropped from the write, not failed — the import still completes."""
    engine = await _make_engine(tmp_path, "pending.sqlite3")
    try:
        rebac = FakeRebac()
        report = await _import(
            _kea_bundle(
                tuples=[
                    {
                        "user": f"user:{UID_UNKNOWN}",
                        "relation": "owner",
                        "object": "team:T1",
                    }
                ],
                realm={
                    "groups": [{"id": "T1", "name": "team1"}],
                    "users": [{"id": UID_UNKNOWN, "username": "ghost"}],
                },
            ),
            engine,
            rebac=rebac,
        )
        assert rebac.relations == []
        assert report.tuples_written == 0
        assert any("PENDING first login" in w and "ghost" in w for w in report.warnings)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_relinked_user_uses_the_swift_side_sub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When swift Keycloak has the same username under a DIFFERENT sub than kea
    (the broker did not preserve subs), the relation is written under the
    swift-side sub, not silently dropped or written under the wrong (kea) sub."""
    swift_sub_for_bob = "99999999-9999-9999-9999-999999999999"

    async def _fake_find_user_subs_bulk(_deps: object) -> dict[str, str]:
        return {"bob": swift_sub_for_bob}

    monkeypatch.setattr(
        "control_plane_backend.import_export.kea_reconciliation.find_user_subs_bulk",
        _fake_find_user_subs_bulk,
    )
    engine = await _make_engine(tmp_path, "relinked.sqlite3")
    try:
        rebac = FakeRebac()
        report = await _import(
            _kea_bundle(
                tuples=[
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "owner",
                        "object": "team:T1",
                    }
                ],
                realm={
                    "groups": [{"id": "T1", "name": "team1"}],
                    "users": [{"id": UID_BOB, "username": "bob"}],
                },
            ),
            engine,
            rebac=rebac,
        )
        written = {_rel_key(r) for r in rebac.relations}
        assert (f"user:{swift_sub_for_bob}", "team_admin", "team:T1") in written
        assert not any(f"user:{UID_BOB}" == k[0] for k in written)
        assert any("RELINKED" in w and "bob" in w for w in report.warnings)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plain_member_restored_from_keycloak_group_membership(
    tmp_path: Path,
) -> None:
    """The core fix: kea never persists a `member` OpenFGA tuple (main derives it
    live from the JWT `groups` claim) — this only source is the realm export's own
    `users[].groups`. Liam is a plain member (no OpenFGA tuple at all for him on
    this team) and must still receive `team_member`."""
    engine = await _make_engine(tmp_path, "plainmember.sqlite3")
    try:
        rebac = FakeRebac()
        report = await _import(
            _kea_bundle(
                tuples=[
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "owner",
                        "object": "team:team-nb",
                    },
                    # No tuple at all for liam — he is only a Keycloak group member.
                ],
                realm={
                    "groups": [{"id": "team-nb", "name": "northbridge"}],
                    "users": [
                        {"id": UID_BOB, "username": "bob", "groups": ["/northbridge"]},
                        {
                            "id": UID_LIAM,
                            "username": "liam",
                            "groups": ["/northbridge"],
                        },
                    ],
                },
            ),
            engine,
            rebac=rebac,
        )
        written = {_rel_key(r) for r in rebac.relations}
        assert (f"user:{UID_LIAM}", "team_member", "team:team-nb") in written
        # Bob is owner -> team_admin/team_editor, and must NOT also get a redundant
        # direct team_member tuple (schema.fga derives it).
        assert (f"user:{UID_BOB}", "team_admin", "team:team-nb") in written
        assert (f"user:{UID_BOB}", "team_member", "team:team-nb") not in written
        assert report.tuples_written == 3  # organization + team_admin/editor + member
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_less_team_is_warned_loudly(tmp_path: Path) -> None:
    """A team with plain members but no owner/manager anywhere in the bundle ends
    up with zero team_admin after import — nothing else in this write path
    enforces the "every team has an admin" invariant, so it must be surfaced."""
    engine = await _make_engine(tmp_path, "adminless.sqlite3")
    try:
        rebac = FakeRebac()
        report = await _import(
            _kea_bundle(
                tuples=[
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "member",
                        "object": "team:team-nb",
                    }
                ],
                realm={
                    "groups": [{"id": "team-nb", "name": "northbridge"}],
                    "users": [
                        {"id": UID_BOB, "username": "bob", "groups": ["/northbridge"]}
                    ],
                },
            ),
            engine,
            rebac=rebac,
        )
        assert any("ZERO team_admin" in w and "team-nb" in w for w in report.warnings)
    finally:
        await engine.dispose()


# ── KeaUserResolver: bulk-snapshot-is-authoritative regression coverage ───────
#
# The bug: `KeaUserResolver.find_sub` used to fall back to a per-username
# `find_user_sub_by_username` Keycloak Admin API call whenever a username was
# missing from the bulk prefetch — exactly the case for ~1899 of ~1900 kea
# usernames on a first cutover import (swift Keycloak starts with only the
# root admin). That silently turned the "one bulk sweep" optimization back
# into ~1900 individual round trips, slow enough to blow past the dry-run's
# HTTP timeout. The fix: a successful bulk sweep (`find_user_subs_bulk`) is now
# the single, authoritative source `find_sub` ever consults — present in it
# resolves, absent from it is PENDING immediately, no fallback call, ever.


@pytest.mark.asyncio
async def test_bulk_snapshot_authoritative_no_individual_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production scenario, at small scale: a username missing from the bulk
    snapshot — whether the snapshot is empty or only carries the root admin —
    must resolve to PENDING off that snapshot alone. Zero calls to
    `find_user_sub_by_username`, ever."""
    individual_calls = 0

    async def _spy_find_user_sub_by_username(
        _username: str, _deps: object
    ) -> str | None:
        nonlocal individual_calls
        individual_calls += 1
        return None

    monkeypatch.setattr(
        "control_plane_backend.users.service.find_user_sub_by_username",
        _spy_find_user_sub_by_username,
    )

    root_admin_sub = "00000000-0000-0000-0000-000000000000"

    async def _fake_find_user_subs_bulk(_deps: object) -> dict[str, str]:
        return {"root-admin": root_admin_sub}

    monkeypatch.setattr(
        "control_plane_backend.import_export.kea_reconciliation.find_user_subs_bulk",
        _fake_find_user_subs_bulk,
    )

    resolver = await KeaUserResolver.create(user_deps=_FAKE_USER_DEPS)
    for username in ("kea-user-1", "kea-user-2", "kea-user-3"):
        assert await resolver.find_sub(username) is None
    assert await resolver.find_sub("root-admin") == root_admin_sub

    assert individual_calls == 0


@pytest.mark.asyncio
async def test_username_present_in_bulk_snapshot_resolves_its_sub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_find_user_subs_bulk(_deps: object) -> dict[str, str]:
        return {"bob": UID_BOB}

    monkeypatch.setattr(
        "control_plane_backend.import_export.kea_reconciliation.find_user_subs_bulk",
        _fake_find_user_subs_bulk,
    )

    resolver = await KeaUserResolver.create(user_deps=_FAKE_USER_DEPS)
    assert await resolver.find_sub("bob") == UID_BOB
    assert await resolver.find_sub("ghost") is None


@pytest.mark.asyncio
async def test_remember_resolves_an_identity_created_mid_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_provision_bundle_identities` creates a Keycloak user for a bundle entry
    missing from the bulk snapshot, then `remember()`s it — the very next
    resolution (e.g. the role phase's `_resolve_bundle_usernames`) must see it
    immediately, with no further Keycloak call of any kind."""

    async def _fake_find_user_subs_bulk(_deps: object) -> dict[str, str]:
        return {}

    monkeypatch.setattr(
        "control_plane_backend.import_export.kea_reconciliation.find_user_subs_bulk",
        _fake_find_user_subs_bulk,
    )

    resolver = await KeaUserResolver.create(user_deps=_FAKE_USER_DEPS)
    assert await resolver.find_sub("newuser") is None  # PENDING before creation

    resolver.remember("newuser", "brand-new-sub")

    assert await resolver.find_sub("newuser") == "brand-new-sub"


@pytest.mark.asyncio
async def test_bulk_sweep_exception_propagates_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real Keycloak/network failure during the bulk sweep must abort the
    import before any Postgres write — `KeaUserResolver.create` runs before the
    transaction opens, so letting the exception propagate here is what makes
    that guarantee hold."""

    class _KeycloakBulkSweepFailed(Exception):
        pass

    async def _fake_find_user_subs_bulk(_deps: object) -> dict[str, str]:
        raise _KeycloakBulkSweepFailed("realm listing failed")

    monkeypatch.setattr(
        "control_plane_backend.import_export.kea_reconciliation.find_user_subs_bulk",
        _fake_find_user_subs_bulk,
    )

    with pytest.raises(_KeycloakBulkSweepFailed):
        await KeaUserResolver.create(user_deps=_FAKE_USER_DEPS)


@pytest.mark.asyncio
async def test_report_buckets_never_duplicate_the_same_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same kea sub is legitimately resolved from more than one call site
    (relation subjects, agent owner, tag owner, ...) — each must land in
    `report.matched`/`report.pending` exactly once, not once per call site."""

    async def _fake_find_user_subs_bulk(_deps: object) -> dict[str, str]:
        return {"bob": UID_BOB}

    monkeypatch.setattr(
        "control_plane_backend.import_export.kea_reconciliation.find_user_subs_bulk",
        _fake_find_user_subs_bulk,
    )

    resolver = await KeaUserResolver.create(user_deps=_FAKE_USER_DEPS)
    report = KeaReconciliationReport()
    username_by_sub = {UID_BOB: "bob", UID_UNKNOWN: "ghost"}

    for _ in range(2):
        await resolve_user_sub(UID_BOB, username_by_sub, resolver, report)
        await resolve_user_sub(UID_UNKNOWN, username_by_sub, resolver, report)

    assert len(report.matched) == 1
    assert len(report.pending) == 1
