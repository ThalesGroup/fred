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

import base64
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from opensearchpy import AsyncOpenSearch
from opensearchpy import exceptions as os_exceptions
from pydantic import BaseModel, Field

APP_ID = "progress-tracker"
INDEX = os.environ.get("PROGRESS_TRACKER_INDEX", "progress-tracker-tasks")
PINS_INDEX = os.environ.get("PROGRESS_TRACKER_PINS_INDEX", "progress-tracker-pins")
# A pending pin is a short-lived statement of intent ("my next conversation is
# about this task"), so a stale click must not hijack a chat hours later.
PIN_TTL_SECONDS = 30 * 60
CONTROL_PLANE = os.environ.get("CONTROL_PLANE_BASE", "")
# Base of the agent runtime, used only to read back conversation history.
RUNTIME_BASE = os.environ.get("RUNTIME_BASE", "")
# Server-to-server credential for the agent path, invented by this sample
# because Fred has no capability outbound auth yet. Not a platform contract --
# see README.md before copying it into a real application.
SERVICE_KEY = os.environ.get("PROGRESS_TRACKER_SERVICE_KEY", "")
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


def _strip_version(task: dict[str, Any]) -> None:
    for key in ("_doc_id", "_seq_no", "_primary_term"):
        task.pop(key, None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.on_event("startup")
async def ensure_index() -> None:
    """Searching a missing index is an error, so the first read would 500."""

    if not await _client.indices.exists(index=PINS_INDEX):
        await _client.indices.create(
            index=PINS_INDEX,
            body={
                "mappings": {
                    "properties": {
                        "team_id": {"type": "keyword"},
                        "user_sub": {"type": "keyword"},
                        "handle": {"type": "keyword"},
                        "created_at": {"type": "date"},
                    }
                }
            },
        )
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
    # Sent by the capability, never by the UI -- which is exactly what makes it
    # usable as attribution: a write carrying a session came from an agent turn.
    session_id: str | None = Field(default=None, max_length=128)


class Decision(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    answer: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=128)


class PinSession(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    # Sent only on the agent path, where the caller is the runtime rather than
    # a person: it comes from the runtime's own identity, never from the model,
    # so it cannot be steered by a prompt. Ignored when a user bearer is used.
    user_sub: str | None = Field(default=None, max_length=128)


async def require_entitled(
    team_id: str,
    authorization: Annotated[str | None, Header()] = None,
    x_service_key: Annotated[str | None, Header()] = None,
) -> str:
    """Ask the Control Plane the question the gateway does not.

    One call answers both halves, because grants are team to capability: a
    non-member is refused outright, and a member whose team was never granted
    this application sees it absent from the list.

    Two callers, two modes. A person's request carries their bearer and is
    checked as above. The agents pod carries a shared service key instead and
    is trusted on that alone -- no Control Plane call happens on that path, so
    it may not also present a bearer.
    """

    # The agent path presents a service key instead of a user bearer. Compared
    # with compare_digest so a wrong key cannot be recovered from timing.
    if x_service_key is not None:
        if not (SERVICE_KEY and secrets.compare_digest(x_service_key, SERVICE_KEY)):
            raise HTTPException(status_code=403, detail="bad_service_key")
        # The two modes are mutually exclusive on purpose: this path asks the
        # Control Plane nothing, so a bearer arriving beside the key has been
        # vetted by no one, and `_bearer_sub` would still read an identity out
        # of it. Refusing the combination is what keeps that helper honest.
        if authorization:
            raise HTTPException(status_code=400, detail="service_key_with_bearer")
        return team_id

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
            # Search omits these unless asked, and _save needs them to refuse a
            # write built on a version someone else has already replaced.
            "seq_no_primary_term": True,
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
    task["_seq_no"] = hits[0]["_seq_no"]
    task["_primary_term"] = hits[0]["_primary_term"]
    return task


async def _save(task: dict[str, Any]) -> None:
    """Write the task back, refusing to clobber a concurrent update.

    Every write here is read-modify-write on one document, so without a version
    check the last writer silently erases the other's note, decision or session
    link. The conflict is surfaced rather than retried: the caller knows what it
    was appending, this function does not.
    """

    doc_id = task.pop("_doc_id")
    seq_no = task.pop("_seq_no", None)
    primary_term = task.pop("_primary_term", None)
    task["updated_at"] = _now()
    try:
        await _client.index(
            index=INDEX,
            id=doc_id,
            body=task,
            refresh="wait_for",
            if_seq_no=seq_no,
            if_primary_term=primary_term,
        )
    except os_exceptions.ConflictError:
        raise HTTPException(status_code=409, detail="task_changed_concurrently")


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
    _strip_version(task)
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
    _strip_version(task)
    return task


def _bearer_sub(authorization: str | None) -> str | None:
    """Read the caller's subject from a token the Control Plane already accepted.

    Decoding without verifying the signature is only defensible because of
    that: the bearer path in `require_entitled` has had this exact token
    accepted upstream, and the service-key path refuses to carry a bearer at
    all. Lift either condition and this becomes an unauthenticated claim to
    someone else's identity, so callers must keep treating a `None` return as
    "no usable subject" rather than falling back to a caller-supplied one.
    """

    if not authorization or " " not in authorization:
        return None
    token = authorization.split(" ", 1)[1]
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) and sub else None


@app.post("/teams/{team_id}/tasks/{handle}/discuss")
async def discuss_next(
    team_id: Entitled,
    handle: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Mark this task as the subject of the caller's next conversation.

    One pending pin per user per team — a newer click replaces the older one.
    The capability claims it on the first tool call of a session that has no
    task yet, which is what lets the user just start talking.
    """

    sub = _bearer_sub(authorization)
    if sub is None:
        raise HTTPException(status_code=401, detail="unreadable_subject")
    await _get(team_id, handle)  # 404s before pinning something unopenable
    await _client.index(
        index=PINS_INDEX,
        id=f"{team_id}:{sub}",
        body={
            "team_id": team_id,
            "user_sub": sub,
            "handle": handle,
            "created_at": _now(),
        },
        refresh="wait_for",
    )
    return {"handle": handle, "expires_in_seconds": PIN_TTL_SECONDS}


@app.post("/teams/{team_id}/discuss/claim")
async def claim_pending_pin(
    team_id: Entitled,
    body: PinSession,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Attach the caller's pending pin, if any, to this conversation.

    The conditional delete is the claim itself: OpenSearch has no
    transactions, so two concurrent sessions both read the pin and only the
    one whose seq_no still matches wins the delete — the loser sees a
    conflict and reports no pin, never a double-claim.
    """

    # A service-key call carries no user token to read a subject from, so the
    # runtime supplies the acting user instead. A browser call always derives
    # it from the bearer, so a person cannot claim someone else's pin.
    sub = _bearer_sub(authorization) or (body.user_sub if authorization is None else None)
    if sub is None:
        raise HTTPException(status_code=401, detail="unreadable_subject")
    doc_id = f"{team_id}:{sub}"
    try:
        pin = await _client.get(index=PINS_INDEX, id=doc_id)
    except os_exceptions.NotFoundError:
        return {"claimed": False}

    if _age_seconds(pin["_source"].get("created_at")) > PIN_TTL_SECONDS:
        await _drop_pin(doc_id, pin)
        return {"claimed": False}

    # Link first, consume second. The reverse order spends the pin before the
    # link is durable, so a failure in between loses the intent with nothing
    # left to retry. Linking twice is harmless -- the append is idempotent --
    # while losing the pin is not.
    task = await _get(team_id, pin["_source"]["handle"])
    if body.session_id not in task["session_ids"]:
        task["session_ids"].append(body.session_id)
        await _save(task)

    # The conditional delete is the claim: two sessions can both link, but only
    # the one whose seq_no still matches consumes the pin and reports success.
    if not await _drop_pin(doc_id, pin):
        return {"claimed": False}
    _strip_version(task)
    return {"claimed": True, "task": task}


async def _drop_pin(doc_id: str, pin: dict[str, Any]) -> bool:
    try:
        await _client.delete(
            index=PINS_INDEX,
            id=doc_id,
            if_seq_no=pin["_seq_no"],
            if_primary_term=pin["_primary_term"],
            refresh="wait_for",
        )
    except (os_exceptions.ConflictError, os_exceptions.NotFoundError):
        return False
    return True


def _age_seconds(stamp: str | None) -> float:
    if not stamp:
        return float("inf")
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return float("inf")
    return (datetime.now(timezone.utc) - then).total_seconds()


@app.delete("/teams/{team_id}/discuss")
async def drop_pending_pin(
    team_id: Entitled,
    body: PinSession,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Discard the caller's pending pin because the intent is already served.

    Resuming a conversation that is already linked satisfies the same intent a
    pin exists to carry. Left behind, that pin would be claimed by whatever
    unrelated conversation the user opened next, silently attaching it to this
    task.
    """

    sub = _bearer_sub(authorization) or (body.user_sub if authorization is None else None)
    if sub is None:
        raise HTTPException(status_code=401, detail="unreadable_subject")
    try:
        await _client.delete(
            index=PINS_INDEX, id=f"{team_id}:{sub}", refresh="wait_for"
        )
    except os_exceptions.NotFoundError:
        return {"dropped": False}
    return {"dropped": True}


@app.get("/teams/{team_id}/tasks/{handle}/conversations")
async def task_conversations(
    team_id: Entitled,
    handle: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Read back the conversations pinned to this task.

    The runtime returns only rows belonging to the authenticated user and an
    empty list for anyone else's session, so this is per-viewer by construction:
    forwarding the caller's own bearer is what keeps a teammate's transcript
    unreadable here.
    """

    task = await _get(team_id, handle)
    if not RUNTIME_BASE:
        return {"items": [], "unavailable": "runtime_not_configured"}

    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for session_id in task.get("session_ids", []):
            url = f"{RUNTIME_BASE}/agents/sessions/{session_id}/messages"
            try:
                response = await client.get(
                    url, headers={"authorization": authorization or ""}
                )
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            items.append(
                {
                    "session_id": session_id,
                    "messages": _readable(response.json()),
                }
            )
    return {"items": items}


def _readable(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep what a person would recognise as the conversation.

    Plans, thoughts, tool calls and their results are dropped: this view exists
    to show what was said, not to replay the agent's working.
    """

    out = []
    for message in messages:
        if message.get("role") not in ("user", "assistant"):
            continue
        if message.get("channel") != "final":
            continue
        text = "\n".join(
            part.get("text", "")
            for part in message.get("parts", [])
            if part.get("type") == "text"
        ).strip()
        if not text:
            continue
        out.append(
            {
                "role": message["role"],
                "at": message.get("timestamp"),
                "text": text,
            }
        )
    return out


@app.post("/teams/{team_id}/tasks/{handle}/notes", status_code=201)
async def add_note(team_id: Entitled, handle: str, body: Note) -> dict[str, Any]:
    task = await _get(team_id, handle)
    task["notes"].append(
        {
            "at": _now(),
            "text": body.text,
            "session_id": body.session_id,
            "source": "agent" if body.session_id else "ui",
        }
    )
    await _save(task)
    _strip_version(task)
    return task


@app.post("/teams/{team_id}/tasks/{handle}/decisions", status_code=201)
async def record_decision(
    team_id: Entitled, handle: str, body: Decision
) -> dict[str, Any]:
    """Checkpoint a decision. This is the record later agent turns rely on."""

    task = await _get(team_id, handle)
    task["decisions"].append(
        {
            "at": _now(),
            "question": body.question,
            "answer": body.answer,
            "session_id": body.session_id,
            "source": "agent" if body.session_id else "ui",
        }
    )
    task["stage"] = "decided"
    await _save(task)
    _strip_version(task)
    return task
