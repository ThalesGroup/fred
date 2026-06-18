from __future__ import annotations

import logging

import httpx
from fred_sdk.contracts.eval import EvalTrace
from fred_sdk.contracts.execution import ExecutionGrant

logger = logging.getLogger(__name__)


class AgentClient:
    def __init__(self, *, timeout_seconds: int = 600) -> None:
        self._timeout = timeout_seconds

    async def evaluate(
        self,
        *,
        evaluate_url: str,
        execution_grant: ExecutionGrant,
        agent_id: str,
        session_id: str,
        input: str,
    ) -> EvalTrace:
        token = execution_grant.model_dump_json()
        headers = {
            "Content-Type": "application/json",
            "X-Execution-Grant": token,
        }
        body = {
            "agent_id": agent_id,
            "session_id": session_id,
            "input": input,
        }
        logger.info(
            "[AGENT-CLIENT] POST %s agent=%s session=%s",
            evaluate_url,
            agent_id,
            session_id,
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(evaluate_url, headers=headers, json=body)
            response.raise_for_status()
            return EvalTrace.model_validate(response.json())
