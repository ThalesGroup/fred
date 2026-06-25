from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Ingestion (upload + process) can take a while; queries are quick.
_INGEST_TIMEOUT = 120.0
_DEFAULT_TIMEOUT = 30.0


class KnowledgeFlowError(RuntimeError):
    """Raised when a Knowledge Flow call fails in a way a step should report."""


class KnowledgeFlowClient:
    """Thin server-side client the self-test harness uses to drive Knowledge Flow.

    Auth is bearer-token pass-through: the campaign runs on behalf of the admin
    who triggered it, reusing their token (same pattern as product/service.py).
    """

    def __init__(self, base_url: str, authorization: str | None) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": authorization} if authorization else {}

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def create_library(self, *, name: str, description: str, team_id: str) -> str:
        """Create a document library (tag) for the team. Returns its id.

        Idempotent: if the library already exists (e.g. a previous keep_corpus
        run), reuse it instead of failing on the 409.
        """
        payload = {
            "name": name,
            "description": description,
            "type": "document",
            "team_id": team_id,
        }
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                self._url("/tags"), json=payload, headers=self._headers
            )
        if resp.status_code == 409:
            existing = await self._find_library_id(name)
            if existing:
                return existing
            raise KnowledgeFlowError(
                f"create_library({name}) -> 409 but no existing library found"
            )
        if resp.status_code >= 400:
            raise KnowledgeFlowError(
                f"create_library({name}) -> {resp.status_code}: {resp.text[:300]}"
            )
        tag_id = resp.json().get("id")
        if not tag_id:
            raise KnowledgeFlowError(f"create_library({name}) returned no id")
        return str(tag_id)

    async def _find_library_id(self, name: str) -> str | None:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(self._url("/tags"), headers=self._headers)
        if resp.status_code >= 400:
            return None
        body = resp.json()
        items = body if isinstance(body, list) else body.get("tags", [])
        for tag in items:
            if tag.get("name") == name and tag.get("type") == "document":
                tag_id = tag.get("id") or tag.get("tag_id")
                if tag_id:
                    return str(tag_id)
        return None

    async def ingest_document(
        self, *, library_id: str, filename: str, text: str
    ) -> str:
        """Upload and process one text document into a library. Returns its uid."""
        # "fred" is the standard push source for user uploads (Knowledge Flow's
        # document_sources config); it must be a configured tag, not an invented one.
        metadata = {"tags": [library_id], "source_tag": "fred"}
        files = {"files": (filename, text.encode("utf-8"), "text/markdown")}
        data = {"metadata_json": json.dumps(metadata)}
        async with httpx.AsyncClient(timeout=_INGEST_TIMEOUT) as client:
            resp = await client.post(
                self._url("/upload-process-documents"),
                files=files,
                data=data,
                headers=self._headers,
            )
        if resp.status_code >= 400:
            raise KnowledgeFlowError(
                f"ingest_document({filename}) -> {resp.status_code}: {resp.text[:300]}"
            )
        # /upload-process-documents streams NDJSON: success events carry a
        # document_uid; a fast failure carries a FAILED event (and a `done`
        # event) with the real error. Surface that error rather than a generic
        # "no document_uid" so the harness reports the actual cause.
        uid, stream_error = _parse_ingestion_stream(resp.text)
        if uid:
            return uid
        if stream_error:
            raise KnowledgeFlowError(
                f"ingest_document({filename}) failed: {stream_error}"
            )
        raise KnowledgeFlowError(
            f"ingest_document({filename}) returned no document_uid; "
            f"response: {resp.text[:300]}"
        )

    async def search(
        self,
        *,
        question: str,
        owner_filter: str,
        team_id: str | None,
        library_id: str | None = None,
        document_uid: str | None = None,
        search_policy: str = "hybrid",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Run a scoped search. Returns the raw hit dicts (content/uid/score).

        Scope by ``library_id`` (filters chunks on metadata.tag_ids) or by
        ``document_uid`` (filters on metadata.document_uid) — the latter is the
        diagnostic fallback that bypasses tag scoping. owner_filter must match the
        resource ownership ("personal"/"team"); team_id is only used for "team".
        """
        payload: dict[str, Any] = {
            "question": question,
            "top_k": top_k,
            "search_policy": search_policy,
            "owner_filter": owner_filter,
        }
        if document_uid is not None:
            payload["document_uids"] = [document_uid]
        if library_id is not None:
            payload["document_library_tags_ids"] = [library_id]
        if owner_filter == "team" and team_id:
            payload["team_id"] = team_id
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                self._url("/vector/search"), json=payload, headers=self._headers
            )
        if resp.status_code >= 400:
            raise KnowledgeFlowError(f"search -> {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        # Endpoint may return a bare list or an envelope with a results key.
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for key in ("hits", "results", "documents"):
                if isinstance(body.get(key), list):
                    return body[key]
        return []

    async def delete_document(self, document_uid: str) -> None:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.delete(
                self._url(f"/fast/delete/{document_uid}"), headers=self._headers
            )
        if resp.status_code >= 400 and resp.status_code != 404:
            raise KnowledgeFlowError(
                f"delete_document({document_uid}) -> {resp.status_code}: {resp.text[:300]}"
            )

    async def delete_library(self, library_id: str) -> None:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.delete(
                self._url(f"/tags/{library_id}"), headers=self._headers
            )
        if resp.status_code >= 400 and resp.status_code != 404:
            raise KnowledgeFlowError(
                f"delete_library({library_id}) -> {resp.status_code}: {resp.text[:300]}"
            )


def _parse_ingestion_stream(body: str) -> tuple[str | None, str | None]:
    """Parse the NDJSON upload stream into (document_uid, error).

    Returns the last non-empty document_uid seen (success), and the last error
    message carried by a FAILED or `done` event (fast failure). Either may be
    None; a uid takes precedence over an error at the call site.
    """
    uid: str | None = None
    error: str | None = None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        found = _find_uid(event)
        if found:
            uid = found
        err = event.get("error")
        if isinstance(err, str) and err:
            error = err
    return uid, error


def _find_uid(event: Any) -> str | None:
    if isinstance(event, dict):
        for key in ("document_uid", "uid", "document_id"):
            value = event.get(key)
            if isinstance(value, str) and value:
                return value
        for value in event.values():
            found = _find_uid(value)
            if found:
                return found
    elif isinstance(event, list):
        for item in event:
            found = _find_uid(item)
            if found:
                return found
    return None
