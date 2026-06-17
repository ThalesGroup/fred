from __future__ import annotations

import logging
from datetime import datetime

import httpx
from fred_sdk.contracts.execution import ExecutionGrant
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RuntimeAgentExecutionPreparation(BaseModel):
    runtime_id: str
    agent_id: str
    team_id: str
    evaluate_url: str
    execution_grant: ExecutionGrant
    expires_at: datetime


class ManagedInstanceExecutionPreparation(BaseModel):
    agent_instance_id: str
    runtime_id: str
    team_id: str
    evaluate_url: str
    execution_grant: ExecutionGrant
    expires_at: datetime


class ControlPlaneClient:
    def __init__(
        self,
        base_url: str,
        service_token: str | None = None,
        runtime_base_url: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._runtime_base_url = runtime_base_url.rstrip("/")

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._service_token:
            headers["Authorization"] = f"Bearer {self._service_token}"
        return headers

    async def prepare_runtime_agent_execution(
        self,
        *,
        team_id: str,
        runtime_id: str,
        agent_id: str,
    ) -> RuntimeAgentExecutionPreparation:
        url = (
            f"{self._base_url}/teams/{team_id}"
            f"/runtimes/{runtime_id}/agents/{agent_id}/prepare-execution"
        )
        logger.info(
            "[CP-CLIENT] prepare_runtime_agent_execution team=%s runtime=%s agent=%s",
            team_id,
            runtime_id,
            agent_id,
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            evaluate_url = data.get("evaluate_url", "")
            if evaluate_url.startswith("/") and self._runtime_base_url:
                data = {**data, "evaluate_url": f"{self._runtime_base_url}{evaluate_url}"}
            return RuntimeAgentExecutionPreparation.model_validate(data)

    async def prepare_managed_instance_execution(
        self,
        *,
        team_id: str,
        agent_instance_id: str,
    ) -> ManagedInstanceExecutionPreparation:
        url = (
            f"{self._base_url}/teams/{team_id}"
            f"/agent-instances/{agent_instance_id}/prepare-execution"
        )
        logger.info(
            "[CP-CLIENT] prepare_managed_instance_execution team=%s instance=%s",
            team_id,
            agent_instance_id,
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            execute_url = data["execute_url"]
            if execute_url.startswith("/") and self._runtime_base_url:
                execute_url = f"{self._runtime_base_url}{execute_url}"
            evaluate_url = execute_url.replace("/agents/execute", "/agents/evaluate")
            return ManagedInstanceExecutionPreparation(
                agent_instance_id=agent_instance_id,
                runtime_id=data["runtime_id"],
                team_id=str(data["team_id"]),
                evaluate_url=evaluate_url,
                execution_grant=ExecutionGrant.model_validate(data["execution_grant"]),
                expires_at=data["expires_at"],
            )
