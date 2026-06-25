from __future__ import annotations

from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user, require_admin

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.config.models import SelfTestConfig
from control_plane_backend.self_test import engine
from control_plane_backend.self_test.engine import SelfTestEngine
from control_plane_backend.self_test.models import (
    SelfTestRun,
    StartSelfTestResponse,
)


def _self_test_config(request: Request) -> SelfTestConfig:
    container = get_application_container(request)
    config: SelfTestConfig = container.configuration.self_test
    if not config.enabled:
        # 404 (not 403): when disabled the harness simply does not exist.
        raise HTTPException(status_code=404, detail="Self-test harness is disabled")
    return config


def build_self_test_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["self-test"])

    @router.post(
        "/self-test/runs", status_code=202, response_model=StartSelfTestResponse
    )
    async def start_run(
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        config: Annotated[SelfTestConfig, Depends(_self_test_config)],
    ) -> StartSelfTestResponse:
        require_admin(user)
        container = get_application_container(request)
        self_test_engine = SelfTestEngine(
            knowledge_flow_base_url=container.configuration.platform.knowledge_flow_base_url,
            team_id=config.team_id,
            keep_corpus=config.keep_corpus,
        )
        # Reuse the admin's bearer token for the downstream Knowledge Flow calls.
        run_id = self_test_engine.start(request.headers.get("Authorization"))
        return StartSelfTestResponse(run_id=run_id)

    @router.get("/self-test/runs/{run_id}", response_model=SelfTestRun)
    async def get_run(
        run_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        _: Annotated[SelfTestConfig, Depends(_self_test_config)],
    ) -> SelfTestRun:
        require_admin(user)
        run = engine.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    @router.get("/self-test/runs/{run_id}/events")
    async def stream_run_events(
        run_id: str,
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        _: Annotated[SelfTestConfig, Depends(_self_test_config)],
    ) -> StreamingResponse:
        require_admin(user)
        queue = engine.get_queue(run_id)
        if queue is None:
            raise HTTPException(status_code=404, detail="Run not found")

        async def event_source() -> AsyncIterator[str]:
            while True:
                if await request.is_disconnected():
                    break
                event = await queue.get()
                if event is None:  # sentinel: campaign finished
                    break
                yield f"id: {event.seq}\ndata: {event.model_dump_json()}\n\n"

        return StreamingResponse(event_source(), media_type="text/event-stream")

    return router
