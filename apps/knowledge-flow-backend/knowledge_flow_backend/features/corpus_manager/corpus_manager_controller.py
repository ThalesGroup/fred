from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user

from .corpus_manager_service import (
    BuildCorpusTocRequestV1,
    CorpusCapabilitiesV1,
    CorpusManagerService,
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

    def _auth(self, user: KeycloakUser, action: Action = Action.READ):
        authorize_or_raise(user, action, Resource.DOCUMENTS)

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
        async def capabilities(user: KeycloakUser = Depends(get_current_user)):
            self._auth(user, Action.READ)
            try:
                return self.service.capabilities()
            except Exception as e:
                self._handle_exception(e, "capabilities")

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
            self._auth(user, Action.CREATE)
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
            self._auth(user, Action.CREATE)
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
            self._auth(user, Action.CREATE)
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
            self._auth(user, Action.READ)
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
            self._auth(user, Action.READ)
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
            self._auth(user, Action.READ)
            try:
                return self.service.tasks_list(payload)
            except Exception as e:
                self._handle_exception(e, "tasks_list")
