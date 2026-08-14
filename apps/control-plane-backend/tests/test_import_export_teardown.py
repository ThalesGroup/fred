"""Teardown coverage (MIGR-05.18, CONTROL-PLANE-PRODUCT-CONTRACT.md §27).

`run_teardown` must: (a) preserve exactly the union of the root-bootstrap
identity and the calling operator, (b) wipe every OpenFGA tuple touching a
non-preserved user, a team, a tag, or a document while never touching
Keycloak — no `tag#parent@tag` / `document#parent@tag` tuple survives its own
Postgres row being wiped, (c) wipe the six Postgres tables `POST /reset`
never touches on its own (`team_metadata`, `prompt`, `prompt_category`) plus
the three it already did, and (d) be safe to call twice in a row (a retry
after a partial prior run must not raise).
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
from control_plane_backend.models.prompt_models import PromptCategoryRow, PromptRow
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import UserSummary
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
    """Records every reference/type a full teardown asks to wipe."""

    def __init__(self) -> None:
        self.enabled = True
        self.wiped_references: list[RebacReference] = []
        self.wiped_types: list[Resource] = []

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        self.wiped_references.append(reference)
        return None

    async def delete_all_relations_of_type(self, resource_type: Resource) -> int:
        self.wiped_types.append(resource_type)
        return 0


def _user_deps() -> UserServiceDependencies:
    # `list_users` is monkeypatched at the teardown module level in every
    # test below — these dependencies are never dereferenced, only threaded
    # through to satisfy the function signature.
    return UserServiceDependencies(
        configuration=cast(Any, None),
        create_keycloak_admin_client=cast(Any, lambda: None),
    )


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    # agent_instance_models (AgentInstanceRow) and prompt_models (PromptRow) are
    # already imported above — only the task models still need a registration-only import.
    import control_plane_backend.models.task_models  # noqa: F401

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
            PromptCategoryRow(
                category_id="cat-1",
                team_id=TEAM_ID,
                name="Category 1",
            )
        )
        session.add(
            PromptRow(
                prompt_id="prompt-1",
                team_id=TEAM_ID,
                name="Prompt 1",
                category_id="cat-1",
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
            ("prompt_categories", PromptCategoryRow),
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
    """Regression test: `run_teardown` used to delete `PromptRow` but never
    `PromptCategoryRow`, so every prior rehearsal cycle left that team's
    starter-kit categories behind as orphans. A team re-provisioned with the
    same id (e.g. a Kea→Swift rehearsal reset) then failed to re-seed its
    starter kit: `_seed_starter_kit`'s category creates collided with the
    orphaned rows on the `(team_id, name)` unique constraint, and the failure
    was silently swallowed, leaving the team with an empty prompt library."""
    engine = await _make_engine(tmp_path, "teardown-full.sqlite3")
    try:
        await _seed(engine, completed_by=ROOT_UID)
        all_users = [
            _summary(ROOT_UID),
            _summary(CALLER_UID),
            _summary(REGULAR_UID_A),
            _summary(REGULAR_UID_B),
        ]

        async def fake_list_users(
            _current_user: KeycloakUser, _deps: UserServiceDependencies
        ) -> list[UserSummary]:
            return all_users

        monkeypatch.setattr(teardown_impl, "list_users", fake_list_users)

        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        rebac = FakeRebac()
        report = await run_teardown(
            caller=caller,
            engine=engine,
            rebac=cast(Any, rebac),
            user_deps=_user_deps(),
        )

        assert report.preserved_uids == sorted([ROOT_UID, CALLER_UID])

        wiped_user_refs = {
            r.id for r in rebac.wiped_references if r.type == Resource.USER
        }
        assert wiped_user_refs == {REGULAR_UID_A, REGULAR_UID_B}
        assert ROOT_UID not in wiped_user_refs
        assert CALLER_UID not in wiped_user_refs

        # Teams/tags/documents are wiped by type, not by id (self-healing —
        # see teardown.py's module docstring), so no Postgres-derived id
        # needs to appear here for the sweep to have happened.
        assert rebac.wiped_types == [Resource.TEAM, Resource.TAGS, Resource.DOCUMENTS]
        assert report.team_ids_wiped == 1

        counts = await _row_counts(engine)
        assert counts == {
            "agents": 0,
            "tags": 0,
            "documents": 0,
            "teams": 0,
            "prompts": 0,
            "prompt_categories": 0,
        }
        assert report.prompt_categories_deleted == 1

        # The bootstrap row itself is never touched by any teardown step.
        store = PlatformBootstrapStore(engine)
        assert await store.get_completed_by() == ROOT_UID
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_teardown_is_safe_to_retry_after_partial_prior_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a crash right after the OpenFGA-wipe step, before the
    Postgres transaction committed — a retry must converge to the same
    fully-wiped end state without raising."""
    engine = await _make_engine(tmp_path, "teardown-retry.sqlite3")
    try:
        await _seed(engine, completed_by=ROOT_UID)
        all_users = [_summary(ROOT_UID), _summary(CALLER_UID), _summary(REGULAR_UID_A)]

        async def fake_list_users(
            _current_user: KeycloakUser, _deps: UserServiceDependencies
        ) -> list[UserSummary]:
            return all_users

        monkeypatch.setattr(teardown_impl, "list_users", fake_list_users)

        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        report = await run_teardown(
            caller=caller,
            engine=engine,
            rebac=cast(Any, FakeRebac()),
            user_deps=_user_deps(),
        )
        counts = await _row_counts(engine)
        assert all(v == 0 for v in counts.values())

        # Retry on an already-wiped instance must not raise.
        report_retry = await run_teardown(
            caller=caller,
            engine=engine,
            rebac=cast(Any, FakeRebac()),
            user_deps=_user_deps(),
        )
        assert report_retry.preserved_uids == report.preserved_uids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_teardown_sweeps_tag_and_document_tuples_with_no_postgres_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for the orphan-tuple bug: an OpenFGA store can carry
    `tag#parent@tag` / `document#parent@tag` tuples whose Postgres `tag`/
    `metadata` rows are already gone (e.g. wiped by an older, pre-fix build of
    this function, or by a prior `/reset` cycle). An id-driven sweep derived
    from Postgres would see zero ids here and never ask OpenFGA to delete
    anything — this asserts the type-level sweep runs unconditionally instead,
    regardless of what Postgres currently holds."""
    engine = await _make_engine(tmp_path, "teardown-no-pg-rows.sqlite3")
    try:
        # No TagRow/DocumentMetadataRow seeded — Postgres already has none.
        session_factory = make_session_factory(engine)
        async with session_factory() as session, session.begin():
            session.add(
                PlatformBootstrapRow(
                    completed_at=datetime.now(timezone.utc),
                    completed_by=ROOT_UID,
                )
            )

        async def fake_list_users(
            _current_user: KeycloakUser, _deps: UserServiceDependencies
        ) -> list[UserSummary]:
            return [_summary(ROOT_UID), _summary(CALLER_UID)]

        monkeypatch.setattr(teardown_impl, "list_users", fake_list_users)

        caller = KeycloakUser(uid=CALLER_UID, username="operator", roles=[])
        rebac = FakeRebac()
        await run_teardown(
            caller=caller,
            engine=engine,
            rebac=cast(Any, rebac),
            user_deps=_user_deps(),
        )

        assert Resource.TAGS in rebac.wiped_types
        assert Resource.DOCUMENTS in rebac.wiped_types
    finally:
        await engine.dispose()
