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
non-preserved user or any team) and Postgres (agent_instance, tag,
document_metadata, team_metadata, prompt) back to the point right after root
bootstrap. Object storage, vector embeddings, and Keycloak are never touched —
Fred does not own Keycloak identity lifecycle; identity is resolved by
username against a live target Keycloak, never created or destroyed by this
migration tooling (see `docs/swift/ops/KEA_SWIFT_CUTOVER.md`).

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
from sqlalchemy import delete, select
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

    # ── 1. OpenFGA — wipe every tuple for every non-preserved user, and every
    #      tuple referencing any team (role grants, team#organization, …). ──
    all_users = await list_users(caller, user_deps)
    for summary in all_users:
        if summary.id in preserved_uids:
            continue
        await rebac.delete_all_relations_of_reference(
            RebacReference(Resource.USER, summary.id)
        )

    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        team_ids = list(
            (await session.execute(select(TeamMetadataRow.id))).scalars().all()
        )
    for team_id in team_ids:
        await rebac.delete_all_relations_of_reference(
            RebacReference(Resource.TEAM, team_id)
        )
    report.team_ids_wiped = len(team_ids)

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
