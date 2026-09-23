"""Admission and terminal reporting through the runtime's workload credential."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fred_sdk.contracts.runtime import RuntimeStopReason
from pydantic import BaseModel, Field

from fred_runtime.common.outbound_credentials import DelegatedCredentialProvider
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)

logger = logging.getLogger(__name__)


class RunRegistration(BaseModel):
    run_id: str = Field(min_length=1)
    run_ceiling_seconds: float = Field(gt=0, allow_inf_nan=False)
    binding: dict[str, Any] | None = None


async def register_run(
    provider: DelegatedCredentialProvider,
    *,
    http_client: httpx.AsyncClient,
    control_plane_url: str | None,
    agent_instance_id: str | None,
    agent_id: str | None,
    run_ceiling_seconds: float,
) -> RunRegistration:
    if not control_plane_url:
        raise DelegationUnavailableError()
    record = provider.record
    credentials = await provider.credentials()
    body = {
        "agent_instance_id": agent_instance_id,
        "agent_id": agent_id,
        "team_id": record.team_id,
        "started_at": datetime.fromtimestamp(
            record.started_at, timezone.utc
        ).isoformat(),
        "run_ceiling_seconds": run_ceiling_seconds,
        "mode": record.mode,
        "origin_caller": record.origin_caller,
    }
    try:
        response = await http_client.post(
            f"{control_plane_url.rstrip('/')}/agent-runs",
            headers={"Authorization": credentials.authorization or ""},
            params=dict(credentials.parameters),
            json=body,
        )
        if response.status_code in (401, 403):
            raise AuthorityLostError()
        if response.is_error:
            raise DelegationUnavailableError()
        receipt = RunRegistration.model_validate(response.json())
        if receipt.run_id != record.run_id:
            raise DelegationUnavailableError()
        return receipt
    except (AuthorityLostError, DelegationUnavailableError):
        raise
    except Exception:
        raise DelegationUnavailableError() from None


async def report_run_end(
    provider: DelegatedCredentialProvider,
    *,
    http_client: httpx.AsyncClient,
    control_plane_url: str | None,
    outcome: Literal["succeeded", "failed", "cancelled"],
    reason: str | None,
) -> None:
    """Make one bounded report; reporting failure cannot change the local result."""
    if not control_plane_url or not provider.record.registered:
        return
    try:
        authorization = await provider.terminal_authorization()
        try:
            stop_reason = RuntimeStopReason(reason) if reason is not None else None
        except ValueError:
            stop_reason = None
        response = await http_client.post(
            f"{control_plane_url.rstrip('/')}/agent-runs/{quote(provider.run_id, safe='')}/end",
            headers={"Authorization": authorization},
            json={"outcome": outcome, "reason": stop_reason},
            timeout=5.0,
        )
        if response.status_code == 404:
            return
        if response.is_error:
            logger.warning("event=run_end_report outcome=failed reason=receiver_denied")
    except Exception:
        logger.warning("event=run_end_report outcome=failed reason=unavailable")
