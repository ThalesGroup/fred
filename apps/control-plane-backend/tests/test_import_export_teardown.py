"""Full teardown coverage (MIGR-05.18, PLATFORM-IMPORT-RFC.md §9.2).

`run_teardown` must: (a) preserve exactly the union of the root-bootstrap
identity and the calling operator, (b) wipe every other Keycloak user and
every OpenFGA tuple touching a non-preserved user or any team, (c) wipe the
five Postgres tables `POST /reset` never touches on its own
(`team_metadata`, `prompt`) plus the three it already did, and (d) be safe to
call twice in a row (a retry after a partial prior run must not raise).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest
from control_plane_backend.bootstrap.store import PlatformBootstrapStore
from control_plane_backend.import_export import teardown as teardown_impl
from control_plane_backend.import_export.teardown import (
    resolve_preserved_uids,
    run_teardown,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.models.bootstrap_models import PlatformBootstrapRow
from control_plane_backend.models.prompt_models import PromptRow
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import UserNotFoundError, UserSummary
from fred_core import KeycloakUser, RebacReference, Resource
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.models import Base as CoreBase
from fred_core.sql.async_session import make_session_factory
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

ROOT_UID = "00000000-0000-0000-0000-000000000001"
CALLER_UID = "00000000-0000-0000-0000-000000000002"
REGULAR_UID_A = "00000000-0000-0000-0000-000000000003"
REGULAR_UID_B = "00000000-0000-0000-0000-000000000004"
TEAM_ID = "team-fredlab"


class FakeRebac:
    """Records every reference a full teardown asks to wipe."""

    def __init__(self) -> None:
        self.enabled = True
        self.wiped_references: list[RebacReference] = []

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        self.wiped_references.append(reference)
        return None


def _user_deps() -> UserServiceDependencies:
    # `list_users`/`delete_user` are monkeypatched at the teardown module
    # level in every test below — these dependencies are never dereferenced,
    # only threaded through to satisfy the function signature.
    return UserServiceDependencies(
        configuration=cast(Any, None),
        create_keycloak_admin_client=cast(Any, lambda: None),
    )


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import control_plane_backend.models.prompt_models  # noqa: F401
    import fred_core.tasks.orm_models  # noqa: F401

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)
    return engine


async def _seed(engine: AsyncEngine, *, completed_by: str | None) -> None:
    session_factory = make_session_factory(engine)
    async with session_factory() as session, session.begin():
        if completed_by is not None:
            session.add(
                PlatformBootstrapRow(
                    completed_at=datetime.now(timezone.utc),
                    completed_by=completed_by,
                )
            )
        session.add(
            AgentInstanceRow(
                agent_instance_id="agent-1",
                team_id=TEAM_ID,
                template_id="fred:react",
                source_runtime_id="fred",
                source_agent_id="react",
                display_name="Agent 1",
                enabled=True,
            )
        )
        session.add(TagRow(tag_id="tag-1", name="Tag 1", type="document"))
        session.add(DocumentMetadataRow(document_uid="doc-1"))
        session.add(TeamMetadataRow(id=TEAM_ID, name="fredlab"))
        session.add(
            PromptRow(
                prompt_id="prompt-1",
                team_id=TEAM_ID,
                name="Prompt 1",
                text="hello",
            )
        )


async def _row_counts(engine: AsyncEngine) -> dict[str, int]:
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        counts = {}
        for label, model in (
            ("agents", AgentInstanceRow),
            ("tags", TagRow),
            ("documents", DocumentMetadataRow),
            ("teams", TeamMetadataRow),
            ("prompts", PromptRow),
        ):
            counts[label] = (
                await session.execute(select(func.count()).select_from(model))
            ).scalar_one()
        return counts


def _summary(uid: str) -> UserSummary:
    return UserSummary(id=uid, username=uid)


# ── resolve_preserved_uids ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_preserved_uids_is_union_of_bootstrap_and_caller(
    tmp_path: Path,
) -> None:
    engine = await _make_engine(tmp_path, "preserved-union.sqlite3")
    try:
        await _seed(engine, completed_by=ROOT_UID)
        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        preserved = await resolve_preserved_uids(caller, engine)
        assert preserved == {ROOT_UID, CALLER_UID}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_preserved_uids_single_identity_when_caller_is_root(
    tmp_path: Path,
) -> None:
    engine = await _make_engine(tmp_path, "preserved-single.sqlite3")
    try:
        await _seed(engine, completed_by=ROOT_UID)
        caller = KeycloakUser(uid=ROOT_UID, username="root", roles=[])
        preserved = await resolve_preserved_uids(caller, engine)
        assert preserved == {ROOT_UID}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_preserved_uids_no_bootstrap_row_yet(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "preserved-no-bootstrap.sqlite3")
    try:
        await _seed(engine, completed_by=None)
        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        preserved = await resolve_preserved_uids(caller, engine)
        assert preserved == {CALLER_UID}
    finally:
        await engine.dispose()


# ── run_teardown ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_teardown_preserves_identities_wipes_everything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = await _make_engine(tmp_path, "teardown-full.sqlite3")
    try:
        await _seed(engine, completed_by=ROOT_UID)
        all_users = [
            _summary(ROOT_UID),
            _summary(CALLER_UID),
            _summary(REGULAR_UID_A),
            _summary(REGULAR_UID_B),
        ]
        deleted: list[str] = []

        async def fake_list_users(
            _current_user: KeycloakUser, _deps: UserServiceDependencies
        ) -> list[UserSummary]:
            return all_users

        async def fake_delete_user(
            _current_user: KeycloakUser, user_id: str, _deps: UserServiceDependencies
        ) -> None:
            deleted.append(user_id)

        monkeypatch.setattr(teardown_impl, "list_users", fake_list_users)
        monkeypatch.setattr(teardown_impl, "delete_user", fake_delete_user)

        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        rebac = FakeRebac()
        report = await run_teardown(
            caller=caller,
            engine=engine,
            rebac=cast(Any, rebac),
            user_deps=_user_deps(),
        )

        assert report.preserved_uids == sorted([ROOT_UID, CALLER_UID])
        assert sorted(deleted) == sorted([REGULAR_UID_A, REGULAR_UID_B])
        assert report.users_deleted == 2
        assert report.users_delete_failed == []

        wiped_user_refs = {
            r.id for r in rebac.wiped_references if r.type == Resource.USER
        }
        wiped_team_refs = {
            r.id for r in rebac.wiped_references if r.type == Resource.TEAM
        }
        assert wiped_user_refs == {REGULAR_UID_A, REGULAR_UID_B}
        assert ROOT_UID not in wiped_user_refs
        assert CALLER_UID not in wiped_user_refs
        assert wiped_team_refs == {TEAM_ID}

        counts = await _row_counts(engine)
        assert counts == {
            "agents": 0,
            "tags": 0,
            "documents": 0,
            "teams": 0,
            "prompts": 0,
        }

        # The bootstrap row itself is never touched by any teardown step.
        store = PlatformBootstrapStore(engine)
        assert await store.get_completed_by() == ROOT_UID
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_teardown_is_safe_to_retry_after_partial_prior_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a crash right after the Keycloak-delete step: Postgres rows
    still present, but Keycloak already reflects a deleted regular user — the
    second call must not raise on the already-gone identity."""
    engine = await _make_engine(tmp_path, "teardown-retry.sqlite3")
    try:
        await _seed(engine, completed_by=ROOT_UID)
        all_users = [_summary(ROOT_UID), _summary(CALLER_UID), _summary(REGULAR_UID_A)]

        async def fake_list_users(
            _current_user: KeycloakUser, _deps: UserServiceDependencies
        ) -> list[UserSummary]:
            return all_users

        async def fake_delete_user_already_gone(
            _current_user: KeycloakUser, user_id: str, _deps: UserServiceDependencies
        ) -> None:
            raise UserNotFoundError(user_id)

        monkeypatch.setattr(teardown_impl, "list_users", fake_list_users)
        monkeypatch.setattr(teardown_impl, "delete_user", fake_delete_user_already_gone)

        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        report = await run_teardown(
            caller=caller,
            engine=engine,
            rebac=cast(Any, FakeRebac()),
            user_deps=_user_deps(),
        )

        # Already-gone identities are skipped, not reported as failures.
        assert report.users_deleted == 0
        assert report.users_delete_failed == []
        counts = await _row_counts(engine)
        assert all(v == 0 for v in counts.values())
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_teardown_records_keycloak_delete_failures_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = await _make_engine(tmp_path, "teardown-kc-failure.sqlite3")
    try:
        await _seed(engine, completed_by=ROOT_UID)
        all_users = [_summary(ROOT_UID), _summary(CALLER_UID), _summary(REGULAR_UID_A)]

        async def fake_list_users(
            _current_user: KeycloakUser, _deps: UserServiceDependencies
        ) -> list[UserSummary]:
            return all_users

        async def fake_delete_user_boom(
            _current_user: KeycloakUser, user_id: str, _deps: UserServiceDependencies
        ) -> None:
            raise RuntimeError("Keycloak unreachable")

        monkeypatch.setattr(teardown_impl, "list_users", fake_list_users)
        monkeypatch.setattr(teardown_impl, "delete_user", fake_delete_user_boom)

        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        report = await run_teardown(
            caller=caller,
            engine=engine,
            rebac=cast(Any, FakeRebac()),
            user_deps=_user_deps(),
        )

        # A Keycloak failure is surfaced in the report, not raised — Postgres
        # still gets wiped so a retry (which re-attempts the failed user) has
        # as little left to do as possible.
        assert report.users_delete_failed == [REGULAR_UID_A]
        counts = await _row_counts(engine)
        assert all(v == 0 for v in counts.values())
    finally:
        await engine.dispose()
