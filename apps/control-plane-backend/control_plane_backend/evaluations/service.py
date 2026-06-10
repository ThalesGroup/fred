from __future__ import annotations

import logging
from typing import cast, Literal
from uuid import uuid4

from fastapi import HTTPException

from control_plane_backend.evaluations.schemas import (
    CreateEvaluationCampaignRequest,
    CampaignCreatedResponse,
    EvaluationCampaignResponse,
    EvaluationCaseListResponse,
    EvaluationCaseResponse,
    EvaluationMetricResultResponse,
    ManagedInstanceTarget,
    RuntimeAgentTarget,
)
from control_plane_backend.evaluations.store import EvaluationStore

logger = logging.getLogger(__name__)

_MAX_CASES = 200


def _resolve_runtime_target(
    runtime_id: str,
    runtime_catalog_sources: list,
) -> None:
    source = next(
        (
            s
            for s in runtime_catalog_sources
            if s.runtime_id == runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise HTTPException(
            status_code=422,
            detail=f"Runtime '{runtime_id}' is not available or not enabled.",
        )


async def create_campaign(
    request: CreateEvaluationCampaignRequest,
    *,
    created_by: str,
    store: EvaluationStore,
    runtime_catalog_sources: list,
) -> CampaignCreatedResponse:
    if len(request.dataset.cases) > _MAX_CASES:
        raise HTTPException(
            status_code=422,
            detail=f"Dataset exceeds maximum of {_MAX_CASES} cases.",
        )

    if isinstance(request.target, RuntimeAgentTarget):
        _resolve_runtime_target(request.target.runtime_id, runtime_catalog_sources)
        target_kind = "runtime_agent"
        target_runtime_id = request.target.runtime_id
        target_agent_id = request.target.agent_id
        target_instance_id = None
    else:
        target_kind = "managed_instance"
        target_runtime_id = None
        target_agent_id = None
        target_instance_id = request.target.agent_instance_id

    campaign_id = f"eval-cmp-{uuid4().hex[:8]}"

    await store.create_campaign(
        campaign_id=campaign_id,
        name=request.name,
        team_id=request.team_id,
        created_by=created_by,
        target_kind=target_kind,
        target_runtime_id=target_runtime_id,
        target_agent_id=target_agent_id,
        target_instance_id=target_instance_id,
        dataset_name=request.dataset.name,
        dataset_version=request.dataset.version,
        profile=request.profile,
        judge_profile_id=request.judge_profile_id,
        total_cases=len(request.dataset.cases),
    )

    for case_input in request.dataset.cases:
        await store.create_case(
            case_id=f"case-{uuid4().hex[:8]}",
            campaign_id=campaign_id,
            external_id=case_input.external_id,
            input=case_input.input,
            expected_output=case_input.expected_output,
        )

    return CampaignCreatedResponse(
        campaign_id=campaign_id,
        task_id=None,
        state="pending",
    )


def _campaign_row_to_response(row) -> EvaluationCampaignResponse:
    if row.target_kind == "runtime_agent":
        target = RuntimeAgentTarget(
            kind="runtime_agent",
            runtime_id=row.target_runtime_id or "",
            agent_id=row.target_agent_id or "",
        )
    else:
        target = ManagedInstanceTarget(
            kind="managed_instance",
            agent_instance_id=row.target_instance_id or "",
        )

    return EvaluationCampaignResponse(
        campaign_id=row.campaign_id,
        task_id=row.task_id,
        name=row.name,
        team_id=row.team_id,
        created_by=row.created_by,
        target=target,
        dataset_name=row.dataset_name,
        dataset_version=row.dataset_version,
        profile=row.profile,
        judge_profile_id=row.judge_profile_id,
        operational_state=row.operational_state,
        verdict=row.verdict,
        total_cases=row.total_cases,
        completed_cases=row.completed_cases,
        passed_cases=row.passed_cases,
        failed_cases=row.failed_cases,
        execution_error_cases=row.execution_error_cases,
        scoring_error_cases=row.scoring_error_cases,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


async def get_campaign(
    campaign_id: str,
    *,
    store: EvaluationStore,
) -> EvaluationCampaignResponse:
    row = await store.get_campaign(campaign_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Campaign '{campaign_id}' not found."
        )
    return _campaign_row_to_response(row)


async def list_campaigns(
    team_id: str,
    *,
    store: EvaluationStore,
) -> list[EvaluationCampaignResponse]:
    rows = await store.list_campaigns_by_team(team_id)
    return [_campaign_row_to_response(row) for row in rows]


async def list_cases(
    campaign_id: str,
    *,
    offset: int = 0,
    limit: int = 50,
    store: EvaluationStore,
) -> EvaluationCaseListResponse:
    rows = await store.list_cases_by_campaign(campaign_id, offset=offset, limit=limit)
    cases = []
    for row in rows:
        metrics = await store.list_metrics_by_case(row.case_id)
        cases.append(
            EvaluationCaseResponse(
                case_id=row.case_id,
                campaign_id=row.campaign_id,
                external_id=row.external_id,
                status=row.status,
                outcome=row.outcome,
                verdict=row.verdict,
                input=row.input,
                expected_output=row.expected_output,
                actual_output=row.actual_output,
                profile=row.profile,
                latency_ms=row.latency_ms,
                execution_error=row.execution_error,
                scoring_errors=[]
                if not row.scoring_errors_json
                else __import__("json").loads(row.scoring_errors_json),
                metrics=[
                    EvaluationMetricResultResponse(
                        name=m.name,
                        provider=m.provider,
                        score=float(m.score) if m.score is not None else None,
                        threshold=float(m.threshold)
                        if m.threshold is not None
                        else None,
                        verdict=cast(
                            Literal["passed", "failed", "skipped", "error"], m.verdict
                        ),
                        explanation=m.explanation,
                        error=m.error,
                    )
                    for m in metrics
                ],
                started_at=row.started_at,
                completed_at=row.completed_at,
            )
        )
    return EvaluationCaseListResponse(cases=cases, total=len(cases))
