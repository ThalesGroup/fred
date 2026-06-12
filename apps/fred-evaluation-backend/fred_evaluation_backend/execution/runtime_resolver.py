from __future__ import annotations

import logging

from fastapi import HTTPException

from fred_evaluation_backend.execution.control_plane_client import (
    ControlPlaneClient,
    ManagedInstanceExecutionPreparation,
    RuntimeAgentExecutionPreparation,
)

logger = logging.getLogger(__name__)


async def resolve_runtime_agent(
    *,
    team_id: str,
    runtime_id: str,
    agent_id: str,
    control_plane_client: ControlPlaneClient,
) -> RuntimeAgentExecutionPreparation:
    """
    Resolve a runtime_agent target into an execution preparation.

    Calls the Control Plane to validate the runtime exists and obtain
    an ingress-safe evaluate_url + short-lived execution_grant.
    """
    try:
        return await control_plane_client.prepare_runtime_agent_execution(
            team_id=team_id,
            runtime_id=runtime_id,
            agent_id=agent_id,
        )
    except Exception as exc:
        logger.error(
            "[RESOLVER] Failed to resolve runtime=%s agent=%s: %s",
            runtime_id,
            agent_id,
            exc,
        )
        raise HTTPException(
            status_code=422,
            detail=f"Runtime '{runtime_id}' is not available or not enabled.",
        ) from exc


async def resolve_managed_instance(
    *,
    team_id: str,
    agent_instance_id: str,
    control_plane_client: ControlPlaneClient,
) -> ManagedInstanceExecutionPreparation:
    """
    Resolve a managed_instance target into an execution preparation.
    """
    try:
        return await control_plane_client.prepare_managed_instance_execution(
            team_id=team_id,
            agent_instance_id=agent_instance_id,
        )
    except Exception as exc:
        logger.error(
            "[RESOLVER] Failed to resolve managed instance=%s: %s",
            agent_instance_id,
            exc,
        )
        raise HTTPException(
            status_code=422,
            detail=f"Managed instance '{agent_instance_id}' is not available.",
        ) from exc
