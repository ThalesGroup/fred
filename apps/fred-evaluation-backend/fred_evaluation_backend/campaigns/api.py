from __future__ import annotations

import asyncio
import json
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user
from sqlalchemy.ext.asyncio import AsyncEngine

from fred_evaluation_backend.campaigns import service
from fred_evaluation_backend.campaigns.schemas import (
    CampaignCreatedResponse,
    CreateEvaluationCampaignRequest,
    EvaluationCampaignListResponse,
    EvaluationCampaignResponse,
    EvaluationCaseListResponse,
    EvaluationCaseResponse,
)
from fred_evaluation_backend.campaigns.store import EvaluationStore
from fred_evaluation_backend.execution.control_plane_client import ControlPlaneClient


def _get_evaluation_store(request: Request) -> EvaluationStore:
    engine: AsyncEngine = request.app.state.db_engine
    return EvaluationStore(engine)


def _get_control_plane_client(request: Request) -> ControlPlaneClient:
    return request.app.state.control_plane_client


def build_evaluations_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["Evaluations"])

    @router.post(
        "/campaigns",
        status_code=202,
        response_model=CampaignCreatedResponse,
    )
    async def create_campaign(
        body: CreateEvaluationCampaignRequest,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
        cp_client: Annotated[ControlPlaneClient, Depends(_get_control_plane_client)],
    ) -> CampaignCreatedResponse:
        return await service.create_campaign(
            body,
            created_by=user.uid,
            store=store,
            control_plane_client=cp_client,
        )

    @router.get(
        "/campaigns",
        response_model=EvaluationCampaignListResponse,
    )
    async def list_campaigns(
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
        team_id: str = Query(...),
    ) -> EvaluationCampaignListResponse:
        campaigns = await service.list_campaigns(team_id, store=store)
        return EvaluationCampaignListResponse(campaigns=campaigns, total=len(campaigns))

    @router.get(
        "/campaigns/{campaign_id}",
        response_model=EvaluationCampaignResponse,
    )
    async def get_campaign(
        campaign_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
    ) -> EvaluationCampaignResponse:
        return await service.get_campaign(campaign_id, store=store)

    @router.get(
        "/campaigns/{campaign_id}/cases",
        response_model=EvaluationCaseListResponse,
    )
    async def list_cases(
        campaign_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> EvaluationCaseListResponse:
        return await service.list_cases(
            campaign_id, offset=offset, limit=limit, store=store
        )

    @router.get(
        "/campaigns/{campaign_id}/cases/{case_id}",
        response_model=EvaluationCaseResponse,
    )
    async def get_case(
        campaign_id: str,
        case_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
    ) -> EvaluationCaseResponse:
        cases = await service.list_cases(campaign_id, store=store)
        case = next((c for c in cases.cases if c.case_id == case_id), None)
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
        return case

    @router.get("/campaigns/{campaign_id}/events")
    async def stream_events(
        campaign_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
    ) -> StreamingResponse:
        await service.get_campaign(campaign_id, store=store)

        async def event_generator() -> AsyncGenerator[str, None]:
            last_seq = -1
            while True:
                events = await store.list_events(campaign_id, after_seq=last_seq)
                for event in events:
                    last_seq = event.seq
                    data = json.dumps({
                        "seq": event.seq,
                        "kind": event.kind,
                        "payload": json.loads(event.payload_json) if event.payload_json else None,
                    })
                    yield f"data: {data}\n\n"
                campaign_row = await store.get_campaign(campaign_id)
                if campaign_row and campaign_row.operational_state in ("succeeded", "failed", "cancelled"):
                    break
                await asyncio.sleep(1)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @router.post("/campaigns/{campaign_id}/cancel", status_code=202)
    async def cancel_campaign(
        campaign_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
    ) -> dict:
        await service.cancel_campaign(campaign_id, store=store)
        return {"campaign_id": campaign_id, "state": "cancelled"}

    return router