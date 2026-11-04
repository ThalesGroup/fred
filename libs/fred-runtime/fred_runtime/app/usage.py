# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded, best-effort consumption reporting with the pod's own identity."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from urllib.parse import quote

import httpx

from fred_runtime.common.outbound_credentials import get_delegation_runtime
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)
REPORT_TIMEOUT_SECONDS = 2.0
_missing_workload_logged = False


async def report_run_usage(
    authority: TurnAuthority | None, *, exchange_id: str, occurred_at: datetime
) -> None:
    """Use retained facts only: the run's authority may already be closed."""
    global _missing_workload_logged
    if authority is None:
        logger.info("event=run_usage outcome=skipped reason=no_consumption")
        return
    binding = authority.binding
    if not binding.conversation_id:
        logger.info("event=run_usage outcome=skipped reason=no_session")
        return
    if not authority.model_usage:
        logger.info("event=run_usage outcome=skipped reason=no_consumption")
        return
    delegation = get_delegation_runtime()

    try:
        # Token acquisition, renewal and both HTTP attempts share this deadline.
        async with asyncio.timeout(REPORT_TIMEOUT_SECONDS):
            lease = await delegation.workload_token_lease() if delegation else None
            if lease is None:
                if not _missing_workload_logged:
                    logger.info(
                        "event=run_usage outcome=skipped reason=no_workload_token"
                    )
                    _missing_workload_logged = True
                return
            config = get_runtime_context().config
            client = config.control_plane_http_client
            if not config.control_plane_url or client is None:
                logger.warning(
                    "event=run_usage outcome=lost reason=missing_destination"
                )
                return
            body = {
                "occurred_at": occurred_at.isoformat(),
                "models": [
                    {
                        "model_source_id": offer.source_id,
                        "upstream_model_id": offer.upstream_model_id,
                        **usage.model_dump(exclude={"total_tokens"}),
                    }
                    for offer, usage in authority.model_usage.items()
                ],
            }
            url = (
                f"{config.control_plane_url.rstrip('/')}/spaces/{binding.space.id}"
                f"/sessions/{quote(binding.conversation_id, safe='')}"
                f"/exchanges/{quote(exchange_id, safe='')}/usage"
            )
            for attempt in range(2):
                try:
                    response = await client.post(
                        url,
                        json=body,
                        headers={
                            "Authorization": f"Bearer {lease.token}",
                            "Idempotency-Key": authority.usage_report_id,
                        },
                        auth=None,
                        follow_redirects=False,
                    )
                except httpx.TransportError:
                    if attempt == 0:
                        continue
                    logger.warning("event=run_usage outcome=lost reason=network")
                    return
                status = response.status_code
                if status == 401 and attempt == 0 and delegation is not None:
                    replacement = await delegation.workload_token_lease(rejected=lease)
                    if replacement is not None:
                        lease = replacement
                        continue
                if status >= 500 and attempt == 0:
                    continue
                outcome = (
                    "recorded"
                    if status == 204
                    else "conflict"
                    if status == 409
                    else "rejected"
                    if 400 <= status < 500
                    else "lost"
                )
                logger.info("event=run_usage outcome=%s status=%s", outcome, status)
                return
    except TimeoutError:
        logger.warning("event=run_usage outcome=lost reason=timeout")
    except Exception as exc:
        # Neither response bodies nor exception messages may expose credentials.
        logger.warning(
            "event=run_usage outcome=lost reason=error error_type=%s",
            type(exc).__name__,
        )
