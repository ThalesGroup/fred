from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fred_core import DocumentPermission, KeycloakUser, TagPermission, TeamPermission, get_current_user

from knowledge_flow_backend.application_context import get_rebac_engine

from .corpus_manager_service import (
    BuildCorpusTocRequestV1,
    CorpusCapabilitiesV1,
    CorpusManagerService,
    CorpusScopeV1,
    PurgeVectorsRequestV1,
    RevectorizeCorpusRequestV1,
    TaskGetRequestV1,
    TaskListRequestV1,
    TaskResultRequestV1,
)

logger = logging.getLogger(__name__)


class CorpusManagerController:
    """
    HTTP facade for corpus management (mock).
    Mirrors the filesystem controller style: DI via Depends, auth checks, and shared service.
    """

    def __init__(self, router: APIRouter):
        self.service = CorpusManagerService()
        self._register_http_routes(router)

    # ----------- Helpers -----------

    async def _authorize_team(self, user: KeycloakUser, team_id: str) -> None:
        # AUTHZ-05 §27: team-scoped — replaces the previous org-level
        # CAN_READ_CONTENT gate, which any global Keycloak viewer satisfied
        # regardless of team membership.
        #
        # AUTHZ-05 review finding (PR #1957): CAN_READ is `team_member or
        # public` in schema.fga — a non-member of a *public* team would pass
        # this check without ever being a real member. Corpus operations are
        # member-only, so this must use CAN_READ_MEMEBERS (`team_member`
        # alone, no `public`) instead.
        await get_rebac_engine().check_user_team_permission_or_raise(user, TeamPermission.CAN_READ_MEMEBERS, team_id)

    async def _authorize_scope(self, user: KeycloakUser, scope: CorpusScopeV1) -> None:
        # AUTHZ-05 §27: team-scoped via the concrete tags/documents named in
        # the scope. `library_id`/`project_id`-only scopes have no ReBAC
        # object to check against yet, so they are denied rather than
        # silently allowed — default deny (RFC §2.5) over a false sense of
        # scoping.
        rebac = get_rebac_engine()
        if not scope.tag_ids and not scope.document_uids:
            raise HTTPException(
                400,
                "This scope cannot be authorized yet: pass tag_ids or document_uids (library_id/project_id-only scopes are not team-checkable).",
            )
        for tag_id in scope.tag_ids:
            await rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)
        for document_uid in scope.document_uids:
            await rebac.check_user_permission_or_raise(user, DocumentPermission.PROCESS, document_uid)

    def _handle_exception(self, e: Exception, context: str):
        logger.exception("[CORPUS] %s failed", context)
        raise HTTPException(500, "Internal server error")

    # ----------- HTTP routes -----------

    def _register_http_routes(self, router: APIRouter):
        @router.get(
            "/corpus/capabilities",
            tags=["CorpusManager"],
            summary="List available corpus tools",
            operation_id="corpus_capabilities",
            response_model=CorpusCapabilitiesV1,
        )
        async def capabilities(
            team_id: str = Query(..., description="Team to check corpus-tool access for."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            await self._authorize_team(user, team_id)
            try:
                return self.service.capabilities()
            except Exception as e:
                return self._handle_exception(e, "capabilities")

        @router.post(
            "/corpus/build-toc",
            tags=["CorpusManager"],
            summary="Start a TOC build task",
            operation_id="corpus_build_toc",
        )
        async def build_toc(
            payload: BuildCorpusTocRequestV1,
            user: KeycloakUser = Depends(get_current_user),
        ):
            # AUTHZ-05 review finding: the created task is now filed under
            # payload.team_id (tasks_get/tasks_result/tasks_list read scope) —
            # require real membership on it, not just permission on the
            # scoped tags/documents, so a caller cannot file a task under a
            # team_id they do not belong to.
            await self._authorize_team(user, payload.team_id)
            await self._authorize_scope(user, payload.scope)
            try:
                return self.service.build_corpus_toc(payload).model_dump()
            except Exception as e:
                self._handle_exception(e, "build_toc")

        @router.post(
            "/corpus/revectorize",
            tags=["CorpusManager"],
            summary="Start a revectorize task",
            operation_id="corpus_revectorize",
        )
        async def revectorize(
            payload: RevectorizeCorpusRequestV1,
            user: KeycloakUser = Depends(get_current_user),
        ):
            # AUTHZ-05 review finding: see build_toc.
            await self._authorize_team(user, payload.team_id)
            await self._authorize_scope(user, payload.scope)
            try:
                return self.service.revectorize_corpus(payload).model_dump()
            except Exception as e:
                self._handle_exception(e, "revectorize")

        @router.post(
            "/corpus/purge-vectors",
            tags=["CorpusManager"],
            summary="Start a purge vectors task",
            operation_id="corpus_purge_vectors",
        )
        async def purge(
            payload: PurgeVectorsRequestV1,
            user: KeycloakUser = Depends(get_current_user),
        ):
            # AUTHZ-05 review finding: see build_toc.
            await self._authorize_team(user, payload.team_id)
            await self._authorize_scope(user, payload.scope)
            try:
                return self.service.purge_vectors(payload).model_dump()
            except Exception as e:
                self._handle_exception(e, "purge_vectors")

        @router.post(
            "/corpus/tasks/get",
            tags=["CorpusManager"],
            summary="Get task status",
            operation_id="corpus_tasks_get",
        )
        async def tasks_get(
            payload: TaskGetRequestV1,
            user: KeycloakUser = Depends(get_current_user),
        ):
            await self._authorize_team(user, payload.team_id)
            try:
                return self.service.tasks_get(payload).model_dump()
            except Exception as e:
                self._handle_exception(e, "tasks_get")

        @router.post(
            "/corpus/tasks/result",
            tags=["CorpusManager"],
            summary="Get task result (or status if still running)",
            operation_id="corpus_tasks_result",
        )
        async def tasks_result(
            payload: TaskResultRequestV1,
            user: KeycloakUser = Depends(get_current_user),
        ):
            await self._authorize_team(user, payload.team_id)
            try:
                return self.service.tasks_result(payload)
            except Exception as e:
                self._handle_exception(e, "tasks_result")

        @router.post(
            "/corpus/tasks/list",
            tags=["CorpusManager"],
            summary="List tasks with filters",
            operation_id="corpus_tasks_list",
        )
        async def tasks_list(
            payload: TaskListRequestV1,
            user: KeycloakUser = Depends(get_current_user),
        ):
            await self._authorize_team(user, payload.team_id)
            try:
                return self.service.tasks_list(payload)
            except Exception as e:
                self._handle_exception(e, "tasks_list")
