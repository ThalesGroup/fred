from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from .gateway import TemporalGateway

logger = logging.getLogger(__name__)


class TemporalTools:
    """LLM-friendly tools exposing Temporal submit/status."""

    def __init__(self, gateway: TemporalGateway):
        self._gateway = gateway
        self._last_workflow_id: Optional[str] = None
        # expose convenience constructor to hide gateway/provider wiring when desired

        @tool("temporal_submit", return_direct=True)
        async def submit(
            request_text: str,
            target_agent: str,
            project_id: Optional[str] = None,
        ) -> str:
            """Submit a long-running Temporal workflow for the given agent and return submission details as JSON."""
            submission = await self._gateway.submit(
                request_text=request_text,
                project_id=project_id,
                target_agent=target_agent,
                user_id=None,
            )
            self._last_workflow_id = submission.workflow_id
            return _as_json(submission.__dict__)

        @tool("temporal_status", return_direct=True)
        async def status(workflow_id: Optional[str] = None) -> str:
            """Return the current status of a workflow (defaults to the last submitted one) as JSON."""
            wf = workflow_id or self._last_workflow_id
            if not wf:
                return "Aucun workflow connu. Soumets d'abord une requête."
            res = await self._gateway.status(workflow_id=wf)
            self._last_workflow_id = wf
            return _as_json(res.__dict__)

        self._submit_tool = submit
        self._status_tool = status

    def tools(self):
        return [self._submit_tool, self._status_tool]

    @classmethod
    def from_app_context(cls) -> "TemporalTools":
        """
        Build tools using the shared Temporal client provider and configured task queue.
        Keeps callers (agents/demos) decoupled from gateway wiring.
        """
        from agentic_backend.application_context import (
            get_configuration,
            get_temporal_client_provider,
        )

        cfg = get_configuration().scheduler
        if cfg.backend.lower() != "temporal":
            raise RuntimeError(
                f"TemporalTools.from_app_context requires scheduler.backend=temporal (found {cfg.backend})"
            )
        gateway = TemporalGateway(
            provider=get_temporal_client_provider(), task_queue=cfg.temporal.task_queue
        )
        return cls(gateway)


def _as_json(data) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:  # pragma: no cover
        logger.warning("[TemporalTools] JSON dump failed, falling back to str")
        return str(data)
