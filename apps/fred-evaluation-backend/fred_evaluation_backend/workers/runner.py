from __future__ import annotations

import asyncio
import logging
import os
import uuid

from sqlalchemy.ext.asyncio import AsyncEngine

from fred_evaluation_backend.campaigns.store import EvaluationStore
from fred_evaluation_backend.config.models import EvaluationConfig, JudgeProfile
from fred_evaluation_backend.execution.agent_client import AgentClient
from fred_evaluation_backend.execution.control_plane_client import ControlPlaneClient
from fred_evaluation_backend.workers.activities import execute_and_score_case

logger = logging.getLogger(__name__)


def _build_judge(profile: JudgeProfile):
    from deepeval.models.llms import LiteLLMModel

    if profile.provider == "litellm":
        api_key_env = profile.settings.api_key_env or "LITELLM_API_KEY"
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {api_key_env} in environment for judge profile."
            )
        return LiteLLMModel(
            model=profile.model,
            api_key=api_key,
            base_url=profile.settings.api_base,
            request_timeout=profile.settings.request_timeout,
            num_retries=0,
        )

    if profile.provider == "ollama":
        return LiteLLMModel(
            model=f"ollama/{profile.model}",
            api_key="ollama",
            base_url=profile.settings.api_base or "http://localhost:11434",
            request_timeout=profile.settings.request_timeout,
            num_retries=0,
        )

    if profile.provider == "openai":
        from deepeval.models.llms import GPTModel

        api_key_env = profile.settings.api_key_env or "OPENAI_API_KEY"
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {api_key_env} in environment for judge profile."
            )
        return GPTModel(model=profile.model)

    raise ValueError(f"Unsupported judge provider: {profile.provider}")


class CampaignRunner:
    def __init__(
        self,
        *,
        config: EvaluationConfig,
        engine: AsyncEngine,
        cp_client: ControlPlaneClient,
    ) -> None:
        self._config = config
        self._store = EvaluationStore(engine)
        self._cp_client = cp_client
        self._agent_client = AgentClient()
        self._sem = asyncio.Semaphore(config.worker.max_concurrent_cases)
        self._running: set[str] = set()

    async def run_forever(self) -> None:
        logger.info(
            "[RUNNER] starting — max_concurrent=%d poll_interval=%ds",
            self._config.worker.max_concurrent_cases,
            self._config.worker.poll_interval_seconds,
        )
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("[RUNNER] unhandled error in tick")
            await asyncio.sleep(self._config.worker.poll_interval_seconds)

    async def _tick(self) -> None:
        rows = await self._store.list_campaigns_by_state("pending", limit=10)
        for campaign in rows:
            if campaign.campaign_id not in self._running:
                self._running.add(campaign.campaign_id)
                asyncio.create_task(
                    self._run_campaign(campaign),
                    name=f"campaign-{campaign.campaign_id}",
                )

    async def _run_campaign(self, campaign) -> None:
        campaign_id = campaign.campaign_id
        logger.info("[RUNNER] starting campaign=%s", campaign_id)
        try:
            await self._store.update_campaign_state(campaign_id, "running")
            await self._store.create_event(
                campaign_id, kind="campaign_started", payload_json=None
            )
            await self._execute_campaign(campaign)
        except Exception:
            logger.exception("[RUNNER] campaign=%s failed unexpectedly", campaign_id)
            await self._store.update_campaign_aggregates(
                campaign_id,
                completed_cases=0,
                passed_cases=0,
                failed_cases=0,
                execution_error_cases=0,
                scoring_error_cases=0,
                verdict="failed",
                operational_state="error",
            )
        finally:
            self._running.discard(campaign_id)

    async def _execute_campaign(self, campaign) -> None:
        campaign_id = campaign.campaign_id

        # Resolve execution grant from Control Plane
        try:
            if campaign.target_kind == "runtime_agent":
                prep = await self._cp_client.prepare_runtime_agent_execution(
                    team_id=campaign.team_id,
                    runtime_id=campaign.target_runtime_id,
                    agent_id=campaign.target_agent_id,
                )
                evaluate_url = prep.evaluate_url
                execution_grant = prep.execution_grant
            else:
                prep = await self._cp_client.prepare_managed_instance_execution(
                    team_id=campaign.team_id,
                    agent_instance_id=campaign.target_instance_id,
                )
                evaluate_url = prep.evaluate_url
                execution_grant = prep.execution_grant
        except Exception as exc:
            logger.error(
                "[RUNNER] campaign=%s cannot prepare execution: %s", campaign_id, exc
            )
            await self._store.update_campaign_aggregates(
                campaign_id,
                completed_cases=0,
                passed_cases=0,
                failed_cases=0,
                execution_error_cases=campaign.total_cases,
                scoring_error_cases=0,
                verdict="failed",
                operational_state="error",
            )
            return

        # Build judge
        judge_profile = self._config.worker.judge_profiles.get(
            campaign.judge_profile_id
        )
        judge = None
        if judge_profile is not None:
            try:
                judge = _build_judge(judge_profile)
            except Exception as exc:
                logger.warning(
                    "[RUNNER] campaign=%s cannot build judge '%s': %s — proceeding without scoring",
                    campaign_id,
                    campaign.judge_profile_id,
                    exc,
                )

        cases = await self._store.list_cases_by_campaign(campaign_id, limit=10000)

        async def _run_case(case) -> None:
            async with self._sem:
                try:
                    await execute_and_score_case(
                        case_id=case.case_id,
                        campaign_id=campaign_id,
                        input=case.input,
                        expected_output=case.expected_output,
                        agent_id=campaign.target_agent_id or "",
                        session_id=str(uuid.uuid4()),
                        evaluate_url=evaluate_url,
                        execution_grant=execution_grant,
                        profile=campaign.profile,
                        judge=judge,
                        store=self._store,
                        agent_client=self._agent_client,
                    )
                except Exception as exc:
                    logger.error("[RUNNER] case=%s unhandled exception: %s", case.case_id, exc)
                    await self._store.update_case_result(
                        case.case_id,
                        status="error",
                        outcome="execution_error",
                        verdict="failed",
                        actual_output=None,
                        latency_ms=None,
                        execution_error=str(exc),
                        scoring_errors_json=None,
                        structural_checks_json=None,
                    )

        results = await asyncio.gather(*[_run_case(c) for c in cases], return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("[RUNNER] campaign=%s case[%d] unhandled exception: %s", campaign_id, i, result)

        # Compute aggregates
        refreshed = await self._store.list_cases_by_campaign(campaign_id, limit=10000)
        completed = len([c for c in refreshed if c.status in ("completed", "error")])
        passed = len([c for c in refreshed if c.verdict == "passed"])
        failed = len([c for c in refreshed if c.verdict == "failed"])
        exec_errors = len([c for c in refreshed if c.outcome == "execution_error"])
        scoring_errors = len(
            [c for c in refreshed if c.scoring_errors_json is not None]
        )

        campaign_verdict = "passed" if passed == campaign.total_cases else "failed"

        await self._store.update_campaign_aggregates(
            campaign_id,
            completed_cases=completed,
            passed_cases=passed,
            failed_cases=failed,
            execution_error_cases=exec_errors,
            scoring_error_cases=scoring_errors,
            verdict=campaign_verdict,
            operational_state="completed",
        )
        await self._store.create_event(
            campaign_id, kind="campaign_completed", payload_json=None
        )
        logger.info(
            "[RUNNER] campaign=%s completed passed=%d failed=%d",
            campaign_id,
            passed,
            failed,
        )
