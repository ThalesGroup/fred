from __future__ import annotations

import logging
from datetime import datetime, timezone

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_evaluation_backend.campaigns.models import (
    EvaluationCampaignRow,
    EvaluationCaseRow,
    EvaluationEventRow,
    EvaluationMetricResultRow,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class EvaluationStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    # ── Campagnes ─────────────────────────────────────────────────────────────

    async def create_campaign(
        self,
        *,
        campaign_id: str,
        run_id: str,
        name: str,
        team_id: str,
        created_by: str,
        target_kind: str,
        target_runtime_id: str | None,
        target_agent_id: str | None,
        target_instance_id: str | None,
        dataset_name: str,
        dataset_version: str | None,
        profile: str,
        judge_profile_id: str,
        total_cases: int,
        session: AsyncSession | None = None,
    ) -> EvaluationCampaignRow:
        row = EvaluationCampaignRow(
            campaign_id=campaign_id,
            run_id=run_id,
            name=name,
            team_id=team_id,
            created_by=created_by,
            target_kind=target_kind,
            target_runtime_id=target_runtime_id,
            target_agent_id=target_agent_id,
            target_instance_id=target_instance_id,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            profile=profile,
            judge_profile_id=judge_profile_id,
            operational_state="pending",
            verdict="pending",
            total_cases=total_cases,
            created_at=_utcnow(),
        )
        async with use_session(self._sessions, session) as s:
            s.add(row)
        return row

    async def get_campaign(
        self,
        campaign_id: str,
        session: AsyncSession | None = None,
    ) -> EvaluationCampaignRow | None:
        async with use_session(self._sessions, session) as s:
            return await s.get(EvaluationCampaignRow, campaign_id)

    async def list_campaigns_by_state(
        self,
        operational_state: str,
        limit: int = 10,
        session: AsyncSession | None = None,
    ) -> list[EvaluationCampaignRow]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(EvaluationCampaignRow)
                        .where(
                            EvaluationCampaignRow.operational_state == operational_state
                        )
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return list(rows)

    async def list_campaigns_by_team(
        self,
        team_id: str,
        session: AsyncSession | None = None,
    ) -> list[EvaluationCampaignRow]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(EvaluationCampaignRow)
                        .where(EvaluationCampaignRow.team_id == team_id)
                        .order_by(EvaluationCampaignRow.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return list(rows)

    # ── Cas ───────────────────────────────────────────────────────────────────

    async def create_case(
        self,
        *,
        case_id: str,
        campaign_id: str,
        run_id: str,
        external_id: str | None,
        input: str,
        expected_output: str | None,
        session: AsyncSession | None = None,
    ) -> EvaluationCaseRow:
        row = EvaluationCaseRow(
            case_id=case_id,
            campaign_id=campaign_id,
            run_id=run_id,
            external_id=external_id,
            input=input,
            expected_output=expected_output,
            status="pending",
            verdict="pending",
        )
        async with use_session(self._sessions, session) as s:
            s.add(row)
        return row

    async def list_cases_by_campaign(
        self,
        campaign_id: str,
        offset: int = 0,
        limit: int = 50,
        session: AsyncSession | None = None,
    ) -> list[EvaluationCaseRow]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(EvaluationCaseRow)
                        .where(EvaluationCaseRow.campaign_id == campaign_id)
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return list(rows)

    async def get_case(
        self,
        case_id: str,
        session: AsyncSession | None = None,
    ) -> EvaluationCaseRow | None:
        async with use_session(self._sessions, session) as s:
            return await s.get(EvaluationCaseRow, case_id)

    # ── Métriques ─────────────────────────────────────────────────────────────

    async def create_metric_result(
        self,
        *,
        case_id: str,
        campaign_id: str,
        name: str,
        provider: str,
        score: float | None,
        threshold: float | None,
        verdict: str,
        explanation: str | None,
        error: str | None,
        session: AsyncSession | None = None,
    ) -> EvaluationMetricResultRow:
        row = EvaluationMetricResultRow(
            case_id=case_id,
            campaign_id=campaign_id,
            name=name,
            provider=provider,
            score=str(score) if score is not None else None,
            threshold=str(threshold) if threshold is not None else None,
            verdict=verdict,
            explanation=explanation,
            error=error,
        )
        async with use_session(self._sessions, session) as s:
            s.add(row)
        return row

    # ── Événements ───────────────────────────────────────────────────────────────

    async def list_events(
        self,
        campaign_id: str,
        after_seq: int = -1,
        session: AsyncSession | None = None,
    ) -> list[EvaluationEventRow]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(EvaluationEventRow)
                        .where(EvaluationEventRow.campaign_id == campaign_id)
                        .where(EvaluationEventRow.seq > after_seq)
                        .order_by(EvaluationEventRow.seq)
                    )
                )
                .scalars()
                .all()
            )
        return list(rows)

    async def update_campaign_state(
        self,
        campaign_id: str,
        operational_state: str,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(EvaluationCampaignRow, campaign_id)
            if row:
                row.operational_state = operational_state

    async def update_case_result(
        self,
        case_id: str,
        *,
        status: str,
        outcome: str,
        verdict: str,
        actual_output: str | None,
        latency_ms: int | None,
        execution_error: str | None,
        scoring_errors_json: str | None,
        structural_checks_json: str | None,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(EvaluationCaseRow, case_id)
            if row:
                row.status = status
                row.outcome = outcome
                row.verdict = verdict
                row.actual_output = actual_output
                row.latency_ms = latency_ms
                row.execution_error = execution_error
                row.scoring_errors_json = scoring_errors_json
                row.structural_checks_json = structural_checks_json

    async def update_campaign_aggregates(
        self,
        campaign_id: str,
        *,
        completed_cases: int,
        passed_cases: int,
        failed_cases: int,
        execution_error_cases: int,
        scoring_error_cases: int,
        verdict: str,
        operational_state: str,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(EvaluationCampaignRow, campaign_id)
            if row:
                row.completed_cases = completed_cases
                row.passed_cases = passed_cases
                row.failed_cases = failed_cases
                row.execution_error_cases = execution_error_cases
                row.scoring_error_cases = scoring_error_cases
                row.verdict = verdict
                row.operational_state = operational_state

    async def create_event(
        self,
        campaign_id: str,
        *,
        kind: str,
        payload_json: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        from sqlalchemy import func

        async with use_session(self._sessions, session) as s:
            campaign = await s.get(EvaluationCampaignRow, campaign_id)
            run_id = campaign.run_id if campaign else "unknown"
            next_seq_result = await s.execute(
                select(func.coalesce(func.max(EvaluationEventRow.seq), -1) + 1).where(
                    EvaluationEventRow.campaign_id == campaign_id
                )
            )
            next_seq = next_seq_result.scalar() or 0
            event = EvaluationEventRow(
                campaign_id=campaign_id,
                run_id=run_id,
                seq=next_seq,
                kind=kind,
                payload_json=payload_json,
            )
            s.add(event)

    async def list_metrics_by_case(
        self,
        case_id: str,
        session: AsyncSession | None = None,
    ) -> list[EvaluationMetricResultRow]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(EvaluationMetricResultRow).where(
                            EvaluationMetricResultRow.case_id == case_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        return list(rows)
