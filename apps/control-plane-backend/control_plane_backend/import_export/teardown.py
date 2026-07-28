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

"""Test-only platform teardown — back to bootstrap-only state, Keycloak untouched.

CONTROL-PLANE-PRODUCT-CONTRACT.md §27. Wipes OpenFGA (every tuple touching a
non-preserved user, plus every team/tag/document tuple regardless of whether
a matching Postgres row still exists) and Postgres (agent_instance, tag,
document_metadata, team_metadata, prompt) back to the point right after root
bootstrap. Object storage, vector embeddings, and Keycloak are never touched —
Fred does not own Keycloak identity lifecycle; identity is resolved by
username against a live target Keycloak, never created or destroyed by this
migration tooling (see `docs/swift/ops/KEA_SWIFT_CUTOVER.md`).

The team/tag/document sweep is deliberately type-level
(`delete_all_relations_of_type`), not id-driven from Postgres: an id-driven
sweep only clears what a caller already knows to ask for, so any tuple that
went orphan under an *older* build of this function (Postgres row already
gone, OpenFGA tuple left behind) would never be asked for again and would
survive every future run. The type-level sweep reads the live OpenFGA store
itself, so it self-heals that kind of drift instead of only preventing new
occurrences of it.

Every step is delete-if-exists / idempotent on its own, so a crash mid-`run_teardown`
and a retry converge to the same end state — no cross-step transaction is needed
or attempted, the same non-atomicity `run_import` already accepts for its
OpenFGA phase (see importer.py's module docstring).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fred_core import KeycloakUser, RebacEngine, RebacReference, Resource
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.sql.async_session import make_session_factory
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.bootstrap.store import PlatformBootstrapStore
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.prompt_models import PromptRow
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.service import list_users

logger = logging.getLogger(__name__)


@dataclass
class TeardownReport:
    preserved_uids: list[str] = field(default_factory=list)
    team_ids_wiped: int = 0
    agents_deleted: int = 0
    tags_deleted: int = 0
    documents_deleted: int = 0
    teams_deleted: int = 0
    prompts_deleted: int = 0


async def resolve_preserved_uids(caller: KeycloakUser, engine: AsyncEngine) -> set[str]:
    """Union of the durable root-bootstrap identity and the calling operator
    (CONTROL-PLANE-PRODUCT-CONTRACT.md §27) — the only identities teardown
    must never remove.
    """
    preserved = {caller.uid}
    completed_by = await PlatformBootstrapStore(engine).get_completed_by()
    if completed_by:
        preserved.add(completed_by)
    return preserved


async def run_teardown(
    *,
    caller: KeycloakUser,
    engine: AsyncEngine,
    rebac: RebacEngine,
    user_deps: UserServiceDependencies,
) -> TeardownReport:
    """Wipe OpenFGA and Postgres unconditionally. Keycloak is never touched —
    backs `POST /reset-rebac` (CONTROL-PLANE-PRODUCT-CONTRACT.md §27), a
    repeated-rehearsal reset that clears stale OpenFGA tuples and Postgres rows
    between test cycles without discarding Keycloak accounts (e.g. a test user
    created to exercise the PENDING→RELINKED reconciliation path), which the
    narrow `POST /reset` cannot do (it never touches OpenFGA).
    """
    preserved_uids = await resolve_preserved_uids(caller, engine)
    report = TeardownReport(preserved_uids=sorted(preserved_uids))

    # ── 1. OpenFGA. Users are wiped per-id (preserved_uids must be excluded,
    #      so a blanket type sweep would be wrong here). Teams/tags/documents
    #      are wiped by type — see module docstring for why this must not be
    #      id-driven from Postgres. ──
    all_users = await list_users(caller, user_deps)
    for summary in all_users:
        if summary.id in preserved_uids:
            continue
        await rebac.delete_all_relations_of_reference(
            RebacReference(Resource.USER, summary.id)
        )

    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        report.team_ids_wiped = (
            await session.execute(select(func.count()).select_from(TeamMetadataRow))
        ).scalar_one()

    await rebac.delete_all_relations_of_type(Resource.TEAM)
    await rebac.delete_all_relations_of_type(Resource.TAGS)
    await rebac.delete_all_relations_of_type(Resource.DOCUMENTS)

    # ── 2. Postgres, one atomic transaction. ───────────────────────────────
    async with session_factory() as session:
        async with session.begin():
            agents_result = await session.execute(
                delete(AgentInstanceRow).execution_options(synchronize_session=False)
            )
            tags_result = await session.execute(
                delete(TagRow).execution_options(synchronize_session=False)
            )
            docs_result = await session.execute(
                delete(DocumentMetadataRow).execution_options(synchronize_session=False)
            )
            teams_result = await session.execute(
                delete(TeamMetadataRow).execution_options(synchronize_session=False)
            )
            prompts_result = await session.execute(
                delete(PromptRow).execution_options(synchronize_session=False)
            )
    report.agents_deleted = getattr(agents_result, "rowcount", 0)
    report.tags_deleted = getattr(tags_result, "rowcount", 0)
    report.documents_deleted = getattr(docs_result, "rowcount", 0)
    report.teams_deleted = getattr(teams_result, "rowcount", 0)
    report.prompts_deleted = getattr(prompts_result, "rowcount", 0)

    logger.warning(
        "[import-export] reset-rebac by %s: preserved=%s teams_wiped=%d "
        "agents=%d tags=%d documents=%d teams_rows=%d prompts=%d",
        caller.uid,
        report.preserved_uids,
        report.team_ids_wiped,
        report.agents_deleted,
        report.tags_deleted,
        report.documents_deleted,
        report.teams_deleted,
        report.prompts_deleted,
    )
    return report
