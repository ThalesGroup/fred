from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_AGENT_POD_BASE_URL = "http://127.0.0.1:8000/api/v1"


@dataclass(slots=True)
class AgentPodClient:
    """
    Minimal synchronous client for the shared Fred pod HTTP contract.

    Why this class exists:
    - chat and smoke workflows only need two operations: list agents and stream
      one execution
    - keeping those calls here makes the CLI reusable for any compatible pod

    How to use it:
    - instantiate with the pod base URL
    - call `list_agents()` to discover agent ids
    - call `execute(...)` for terminal JSON execution
    - call `stream_events(...)` to collect streamed runtime events

    Example:
    - `client = AgentPodClient(base_url="http://127.0.0.1:8000/fred/agents/v2", http_client=httpx.Client())`
    """

    base_url: str
    http_client: httpx.Client
    token_provider: Callable[[], str | None] | None = None
    metrics_url: str | None = None

    def _auth_headers(self) -> dict[str, str]:
        if self.token_provider is None:
            return {}
        token = self.token_provider()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def list_agents(self) -> list[str]:
        url = f"{self.base_url}/agents"
        print(f"[chat] connecting to pod: GET {url}")
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not all(
            isinstance(agent_id, str) for agent_id in payload
        ):
            raise RuntimeError("Agent list response must be a JSON array of strings.")
        return payload

    def list_templates(self) -> list[dict[str, Any]]:
        response = self.http_client.get(
            f"{self.base_url}/agents/templates", headers=self._auth_headers()
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Templates response must be a JSON array.")
        return payload

    def execute(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        user_id: str,
        team_id: str | None = None,
        agent_instance_id: str | None = None,
        checkpoint_id: str | None = None,
        resume_payload: Any = None,
        inline_tuning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime_context: dict[str, Any] = {"user_id": user_id}
        if team_id:
            runtime_context["team_id"] = team_id
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "input": message,
            "session_id": session_id,
            "runtime_context": runtime_context,
        }
        if agent_instance_id is not None:
            payload["agent_instance_id"] = agent_instance_id
        if checkpoint_id is not None:
            payload["checkpoint_id"] = checkpoint_id
        if resume_payload is not None:
            payload["resume_payload"] = resume_payload
        if inline_tuning:
            payload["inline_tuning"] = inline_tuning
        response = self.http_client.post(
            f"{self.base_url}/agents/execute",
            json=payload,
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("Execute response must be a JSON object.")
        return result

    def evaluate(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        user_id: str,
        team_id: str | None = None,
        agent_instance_id: str | None = None,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        runtime_context: dict[str, Any] = {"user_id": user_id}
        if team_id:
            runtime_context["team_id"] = team_id
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "input": message,
            "session_id": session_id,
            "runtime_context": runtime_context,
        }
        if agent_instance_id is not None:
            payload["agent_instance_id"] = agent_instance_id
        if checkpoint_id is not None:
            payload["checkpoint_id"] = checkpoint_id
        response = self.http_client.post(
            f"{self.base_url}/agents/evaluate",
            json=payload,
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("Evaluate response must be a JSON object.")
        return result

    def stream_events(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        user_id: str,
        team_id: str | None = None,
        agent_instance_id: str | None = None,
        checkpoint_id: str | None = None,
        resume_payload: Any = None,
        inline_tuning: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for event in self.iter_stream_events(
            agent_id=agent_id,
            message=message,
            session_id=session_id,
            user_id=user_id,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            checkpoint_id=checkpoint_id,
            resume_payload=resume_payload,
            inline_tuning=inline_tuning,
        ):
            events.append(event)
        return events

    def iter_stream_events(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        user_id: str,
        team_id: str | None = None,
        agent_instance_id: str | None = None,
        checkpoint_id: str | None = None,
        resume_payload: Any = None,
        inline_tuning: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        runtime_context: dict[str, Any] = {"user_id": user_id}
        if team_id:
            runtime_context["team_id"] = team_id
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "input": message,
            "session_id": session_id,
            "runtime_context": runtime_context,
        }
        if agent_instance_id is not None:
            payload["agent_instance_id"] = agent_instance_id
        if checkpoint_id is not None:
            payload["checkpoint_id"] = checkpoint_id
        if resume_payload is not None:
            payload["resume_payload"] = resume_payload
        if inline_tuning:
            payload["inline_tuning"] = inline_tuning
        with self.http_client.stream(
            "POST",
            f"{self.base_url}/agents/execute/stream",
            json=payload,
            headers=self._auth_headers(),
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                line = (
                    raw_line.decode("utf-8")
                    if isinstance(raw_line, bytes)
                    else raw_line
                )
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ").strip()
                if not data:
                    continue
                event = json.loads(data)
                if not isinstance(event, dict):
                    raise RuntimeError("SSE event payload must be a JSON object.")
                yield event

    def list_sessions(self, user_id: str) -> list[str]:
        url = f"{self.base_url}/agents/sessions"
        response = self.http_client.get(
            url, params={"user_id": user_id}, headers=self._auth_headers()
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Sessions response must be a JSON array.")
        return [str(s) for s in payload]

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        url = f"{self.base_url}/agents/sessions/{session_id}/messages"
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Messages response must be a JSON array.")
        return payload

    def delete_session_messages(self, session_id: str) -> int:
        url = f"{self.base_url}/agents/sessions/{session_id}"
        response = self.http_client.delete(url, headers=self._auth_headers())
        response.raise_for_status()
        return int(response.json().get("deleted", 0))

    def delete_checkpoint(self, session_id: str) -> None:
        url = f"{self.base_url}/agents/checkpoints/{session_id}"
        response = self.http_client.delete(url, headers=self._auth_headers())
        response.raise_for_status()

    def get_checkpoint_stats(self) -> dict[str, Any]:
        url = f"{self.base_url}/agents/checkpoints/_stats"
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    def list_checkpoint_threads(self, *, limit: int = 20) -> list[dict[str, Any]]:
        url = f"{self.base_url}/agents/checkpoints"
        response = self.http_client.get(
            url, params={"limit": limit}, headers=self._auth_headers()
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Checkpoint threads response must be a JSON array.")
        return payload

    def get_checkpoint_thread(self, session_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/agents/checkpoints/{session_id}"
        response = self.http_client.get(url, headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    def get_kpi_turns(self, *, limit: int = 30) -> list[dict[str, Any]]:
        url = f"{self.base_url}/agents/kpi-turns"
        response = self.http_client.get(
            url, params={"limit": limit}, headers=self._auth_headers()
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("KPI turns response must be a JSON array.")
        return payload

    def get_audit_events(self, *, limit: int = 30) -> list[dict[str, Any]]:
        url = f"{self.base_url}/agents/audit-events"
        response = self.http_client.get(
            url, params={"limit": limit}, headers=self._auth_headers()
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Audit events response must be a JSON array.")
        return payload

    def get_metrics_text(self) -> str:
        if not self.metrics_url:
            raise RuntimeError(
                "Metrics URL is not configured. Pass `--metrics-url`, export "
                "`FRED_AGENT_METRICS_URL`, or run from a pod project with "
                "configuration.yaml exposing app.metrics_port."
            )
        print(f"[chat] connecting to metrics: GET {self.metrics_url}")
        response = self.http_client.get(
            self.metrics_url,
            headers={"Accept": "text/plain; version=0.0.4"},
        )
        response.raise_for_status()
        return response.text
