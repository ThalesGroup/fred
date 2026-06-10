from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fred_core import KeycloakUser, get_current_user

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.evaluations import service
from control_plane_backend.evaluations.schemas import (
    CampaignCreatedResponse,
    CreateEvaluationCampaignRequest,
    EvaluationCampaignListResponse,
    EvaluationCampaignResponse,
    EvaluationCaseListResponse,
    EvaluationCaseResponse,
)
from control_plane_backend.evaluations.store import EvaluationStore


def _get_evaluation_store(request: Request) -> EvaluationStore:
    container = get_application_container(request)
    return container.get_evaluation_store()


def build_evaluations_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["Evaluations"])

    @router.post(
        "/evaluation-campaigns",
        status_code=202,
        response_model=CampaignCreatedResponse,
    )
    async def create_campaign(
        body: CreateEvaluationCampaignRequest,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
        request: Request,
    ) -> CampaignCreatedResponse:
        container = get_application_container(request)
        return await service.create_campaign(
            body,
            created_by=user.uid,
            store=store,
            runtime_catalog_sources=container.configuration.platform.runtime_catalog_sources,
        )

    @router.get(
        "/evaluation-campaigns",
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
        "/evaluation-campaigns/{campaign_id}",
        response_model=EvaluationCampaignResponse,
    )
    async def get_campaign(
        campaign_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        store: Annotated[EvaluationStore, Depends(_get_evaluation_store)],
    ) -> EvaluationCampaignResponse:
        return await service.get_campaign(campaign_id, store=store)

    @router.get(
        "/evaluation-campaigns/{campaign_id}/cases",
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
        "/evaluation-campaigns/{campaign_id}/cases/{case_id}",
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
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
        return case

    return router
