"""Progress-tracker application API.

Fred's gateway strips ``/app-services/progress-tracker`` before proxying, so
this service sees ``/teams/<team_id>/...``. It is reached by two callers: the
application UI (through the host, which attaches the caller's bearer) and the
agent capability (server side, with the platform's token).

The gateway authorizes nothing. Every handler below therefore asks the Control
Plane whether the caller may use this application for this team, and fails
closed when that question cannot be answered.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from opensearchpy import AsyncOpenSearch
from pydantic import BaseModel, Field

APP_ID = "progress-tracker"
INDEX = os.environ.get("PROGRESS_TRACKER_INDEX", "progress-tracker-tasks")
CONTROL_PLANE = os.environ.get("CONTROL_PLANE_BASE", "")
OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "https://opensearch:9200")
OPENSEARCH_USER = os.environ.get("OPENSEARCH_USER", "admin")
OPENSEARCH_PASSWORD = os.environ.get("OPENSEARCH_PASSWORD", "")

app = FastAPI(title="progress-tracker")

_client = AsyncOpenSearch(
    hosts=[OPENSEARCH_URL],
    http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
    verify_certs=False,
    ssl_show_warn=False,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.on_event("startup")
async def ensure_index() -> None:
    """Searching a missing index is an error, so the first read would 500."""

    if await _client.indices.exists(index=INDEX):
        return
    await _client.indices.create(
        index=INDEX,
        body={
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "handle": {"type": "keyword"},
                    "team_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "stage": {"type": "keyword"},
                    "session_ids": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                }
            }
        },
    )


class CreateTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Note(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class Decision(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    answer: str = Field(min_length=1, max_length=2000)


class PinSession(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)


async def require_entitled(
    team_id: str, authorization: Annotated[str | None, Header()] = None
) -> str:
    """Ask the Control Plane the question the gateway does not.

    One call answers both halves, because grants are team to capability: a
    non-member is refused outright, and a member whose team was never granted
    this application sees it absent from the list.
    """

    if not authorization:
        raise HTTPException(status_code=401, detail="missing_bearer")
    if not CONTROL_PLANE:
        raise HTTPException(status_code=403, detail="entitlement_check_unconfigured")

    url = f"{CONTROL_PLANE}/control-plane/v1/teams/{team_id}/applications"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"authorization": authorization})
    except httpx.HTTPError:
        # Fail closed: an unreachable Control Plane must never mean "allowed".
        raise HTTPException(status_code=403, detail="entitlement_check_unavailable")

    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="not_a_team_member")
    if response.status_code != 200:
        raise HTTPException(status_code=403, detail="entitlement_check_failed")
    listed = any(item.get("id") == APP_ID for item in response.json().get("items", []))
    if not listed:
        raise HTTPException(status_code=403, detail="app_not_granted_to_team")
    return team_id


Entitled = Annotated[str, Depends(require_entitled)]


async def _get(team_id: str, handle: str) -> dict[str, Any]:
    result = await _client.search(
        index=INDEX,
        body={
            "size": 1,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"team_id": team_id}},
                        {"term": {"handle": handle}},
                    ]
                }
            },
        },
    )
    hits = result["hits"]["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail="task_not_found")
    task = hits[0]["_source"]
    task["_doc_id"] = hits[0]["_id"]
    return task


async def _save(task: dict[str, Any]) -> None:
    doc_id = task.pop("_doc_id")
    task["updated_at"] = _now()
    await _client.index(index=INDEX, id=doc_id, body=task, refresh="wait_for")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/teams/{team_id}/tasks")
async def list_tasks(
    team_id: Entitled, session_id: str | None = Query(default=None)
) -> dict[str, Any]:
    """List the team's tasks, or just the one linked to a conversation."""

    filters: list[dict[str, Any]] = [{"term": {"team_id": team_id}}]
    if session_id:
        filters.append({"term": {"session_ids": session_id}})
    result = await _client.search(
        index=INDEX,
        body={
            "size": 50,
            "sort": [{"created_at": "desc"}],
            "query": {"bool": {"filter": filters}},
        },
    )
    return {"items": [hit["_source"] for hit in result["hits"]["hits"]]}


@app.post("/teams/{team_id}/tasks", status_code=201)
async def create_task(team_id: Entitled, body: CreateTask) -> dict[str, Any]:
    """The user's starting point: record the task, before any agent sees it."""

    doc_id = uuid.uuid4().hex
    task = {
        "id": doc_id,
        # Short and speakable, so a user can name it in chat without an id.
        "handle": f"TASK-{doc_id[:4].upper()}",
        "team_id": team_id,
        "title": body.title,
        "stage": "open",
        "session_ids": [],
        "notes": [],
        "decisions": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await _client.index(index=INDEX, id=doc_id, body=task, refresh="wait_for")
    return task


@app.get("/teams/{team_id}/tasks/{handle}")
async def get_task(team_id: Entitled, handle: str) -> dict[str, Any]:
    task = await _get(team_id, handle)
    task.pop("_doc_id", None)
    return task


@app.post("/teams/{team_id}/tasks/{handle}/sessions")
async def pin_session(
    team_id: Entitled, handle: str, body: PinSession
) -> dict[str, Any]:
    """Link a conversation to this task so later turns resolve it with no question."""

    task = await _get(team_id, handle)
    if body.session_id not in task["session_ids"]:
        task["session_ids"].append(body.session_id)
    await _save(task)
    task.pop("_doc_id", None)
    return task


@app.post("/teams/{team_id}/tasks/{handle}/notes", status_code=201)
async def add_note(team_id: Entitled, handle: str, body: Note) -> dict[str, Any]:
    task = await _get(team_id, handle)
    task["notes"].append({"at": _now(), "text": body.text})
    await _save(task)
    task.pop("_doc_id", None)
    return task


@app.post("/teams/{team_id}/tasks/{handle}/decisions", status_code=201)
async def record_decision(
    team_id: Entitled, handle: str, body: Decision
) -> dict[str, Any]:
    """Checkpoint a decision. This is the record later agent turns rely on."""

    task = await _get(team_id, handle)
    task["decisions"].append(
        {"at": _now(), "question": body.question, "answer": body.answer}
    )
    task["stage"] = "decided"
    await _save(task)
    task.pop("_doc_id", None)
    return task
