from __future__ import annotations

import json
import logging

from fred_sdk.contracts.execution import ExecutionGrant

from fred_evaluation_backend.campaigns.store import EvaluationStore
from fred_evaluation_backend.execution.agent_client import AgentClient

logger = logging.getLogger(__name__)


async def execute_and_score_case(
    *,
    case_id: str,
    campaign_id: str,
    input: str,
    expected_output: str | None,
    agent_id: str | None,
    agent_instance_id: str | None = None,
    session_id: str,
    evaluate_url: str,
    execution_grant: ExecutionGrant,
    service_token: str | None = None,
    profile: str,
    judge,
    store: EvaluationStore,
    agent_client: AgentClient,
) -> None:
    from fred_deepeval_cli.core.evaluator import classify_outcome
    from fred_deepeval_cli.core.profiles import resolve_profile
    from fred_deepeval_cli.core.scorer import score_trace
    from fred_deepeval_cli.core.structural_checks import build_structural_checks

    await store.update_case_result(
        case_id,
        status="running",
        outcome="unknown",
        verdict="inconclusive",
        actual_output=None,
        latency_ms=None,
        execution_error=None,
        scoring_errors_json=None,
        structural_checks_json=None,
    )

    try:
        trace = await agent_client.evaluate(
            evaluate_url=evaluate_url,
            execution_grant=execution_grant,
            agent_id=agent_id,
            agent_instance_id=agent_instance_id,
            session_id=session_id,
            input=input,
            service_token=service_token,
        )
    except Exception as exc:
        logger.error("[ACTIVITY] agent call failed case=%s: %s", case_id, exc)
        await store.update_case_result(
            case_id,
            status="error",
            outcome="execution_error",
            verdict="failed",
            actual_output=None,
            latency_ms=None,
            execution_error=str(exc),
            scoring_errors_json=None,
            structural_checks_json=None,
        )
        await _emit_event(campaign_id, case_id, "case_error", store)
        return

    # Convert EvalTrace to the dict format expected by fred-deepeval-cli internals
    trace_dict = trace.model_dump()

    try:
        outcome = classify_outcome(trace_dict)
        resolved_profile = resolve_profile(trace_dict, explicit_profile=profile)
        structural_checks = build_structural_checks(trace_dict, profile=resolved_profile)

        metrics: list = []
        scoring_errors: list[str] = []
        if judge is not None:
            metrics, scoring_errors = score_trace(
                trace_dict,
                profile=resolved_profile,
                expected_output=expected_output,
                judge=judge,
            )
    except Exception as exc:
        logger.error("[ACTIVITY] scoring failed case=%s: %s", case_id, exc)
        await store.update_case_result(
            case_id,
            status="error",
            outcome="execution_error",
            verdict="failed",
            actual_output=trace.output,
            latency_ms=trace.latency_ms,
            execution_error=str(exc),
            scoring_errors_json=None,
            structural_checks_json=None,
        )
        await _emit_event(campaign_id, case_id, "case_error", store)
        return

    structural_ok = all(c.passed for c in structural_checks)
    metrics_ok = all(m.verdict == "passed" for m in metrics) if metrics else True
    verdict = (
        "passed" if structural_ok and metrics_ok and not scoring_errors else "failed"
    )

    await store.update_case_result(
        case_id,
        status="completed",
        outcome=outcome,
        verdict=verdict,
        actual_output=trace.output,
        latency_ms=trace.latency_ms,
        execution_error=trace.error,
        scoring_errors_json=json.dumps(scoring_errors) if scoring_errors else None,
        structural_checks_json=json.dumps([c.model_dump() for c in structural_checks]),
    )

    for metric in metrics:
        await store.create_metric_result(
            case_id=case_id,
            campaign_id=campaign_id,
            name=metric.name,
            provider=metric.provider,
            score=metric.score,
            threshold=metric.threshold,
            verdict=metric.verdict,
            explanation=metric.explanation,
            error=metric.error,
        )

    await _emit_event(campaign_id, case_id, "case_completed", store)


async def _emit_event(
    campaign_id: str,
    case_id: str,
    kind: str,
    store: EvaluationStore,
) -> None:
    await store.create_event(
        campaign_id,
        kind=kind,
        payload_json=json.dumps({"case_id": case_id}),
    )
