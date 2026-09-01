"""Tools for advancing a task record owned by a Fred application.

The session id comes from the runtime identity and is deliberately not a tool
parameter: a prompt must not be able to move an agent onto another
conversation's task.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

import httpx
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)

PROGRESS_TRACKER_CAPABILITY_ID = "progress_tracker"
APPLICATION_ID = "progress-tracker"

# Server-side address of the application's API. The browser never uses this;
# it reaches the same service through Fred's /app-services/ prefix.
_API_BASE_ENV = "PROGRESS_TRACKER_API_BASE"
_TIMEOUT_SECONDS = 15.0


def _api_base() -> str | None:
    return os.environ.get(_API_BASE_ENV) or None


class ProgressTrackerCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    """Read and advance tasks owned by the progress-tracker application."""

    manifest = CapabilityManifest(
        id=PROGRESS_TRACKER_CAPABILITY_ID,
        version="0.1.0",
        name="capability.progress_tracker.name",
        description="capability.progress_tracker.description",
        icon="checklist",
    )
    ConfigModel = EmptyModel

    def tools(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> Sequence[BaseTool]:
        identity = ctx.identity
        base = _api_base()
        token_provider = getattr(ctx.services, "token_provider", None)

        if base is None:
            logger.warning(
                "[PROGRESS-TRACKER] %s unset; contributing no tools", _API_BASE_ENV
            )
            return ()

        async def call(method: str, path: str, payload: dict | None = None) -> Any:
            headers = {}
            if token_provider is not None:
                # Outbound auth is the platform's job; the capability never
                # holds or forwards a raw credential of its own.
                headers["authorization"] = f"Bearer {token_provider.get_bearer_token(ctx)}"
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.request(
                    method, f"{base}{path}", json=payload, headers=headers
                )
                response.raise_for_status()
                return response.json() if response.content else None

        def team_path(suffix: str = "") -> str:
            return f"/teams/{identity.team_id}/tasks{suffix}"

        @tool
        async def list_open_tasks() -> str:
            """List the open tasks for the current team, with their handles."""

            data = await call("GET", team_path())
            items = data.get("items", [])
            if not items:
                return "No open tasks for this team."
            return "\n".join(
                f"{item['handle']} — {item['title']} [{item['stage']}]" for item in items
            )

        @tool
        async def find_task() -> str:
            """Return the task this conversation is already working on, if any.

            Call this first. When it reports no task, ask the user which one
            they mean and then call pin_task.
            """

            if identity.session_id is None:
                return "No conversation context; ask the user which task, then pin it."
            data = await call("GET", team_path(f"?session_id={identity.session_id}"))
            items = data.get("items", [])
            if not items:
                return "This conversation is not linked to a task yet."
            task = items[0]
            return f"Working on {task['handle']} — {task['title']} [{task['stage']}]"

        @tool
        async def pin_task(handle: str) -> str:
            """Link this conversation to a task so later turns resolve it directly."""

            if identity.session_id is None:
                return "No conversation context; nothing to link."
            task = await call(
                "POST",
                team_path(f"/{handle}/sessions"),
                {"session_id": identity.session_id},
            )
            return f"Linked this conversation to {task['handle']}."

        @tool
        async def add_note(text: str) -> str:
            """Append a progress note to the task this conversation is working on."""

            task = await _pinned(call, team_path, identity.session_id)
            if task is None:
                return "No task linked yet — call find_task, then pin_task."
            await call("POST", team_path(f"/{task['handle']}/notes"), {"text": text})
            return f"Noted on {task['handle']}."

        @tool
        async def record_decision(question: str, answer: str) -> str:
            """Checkpoint a decision the user has taken, so later work can rely on it.

            Record only what the user actually decided, in their words.
            """

            task = await _pinned(call, team_path, identity.session_id)
            if task is None:
                return "No task linked yet — call find_task, then pin_task."
            await call(
                "POST",
                team_path(f"/{task['handle']}/decisions"),
                {"question": question, "answer": answer},
            )
            return f"Recorded on {task['handle']}: {question} -> {answer}"

        return [list_open_tasks, find_task, pin_task, add_note, record_decision]


async def _pinned(call: Any, team_path: Any, session_id: str | None) -> dict | None:
    if session_id is None:
        return None
    data = await call("GET", team_path(f"?session_id={session_id}"))
    items = data.get("items", [])
    return items[0] if items else None
