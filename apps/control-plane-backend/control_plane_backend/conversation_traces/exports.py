# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Assemble a bounded trace ZIP in memory from the authenticated runtime reads."""

import asyncio
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Coroutine
from dataclasses import dataclass, field
from io import BytesIO
from itertools import batched
from typing import Literal, Protocol, TypeVar
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

import anyio
from fastapi import HTTPException
from fred_core.conversation_trace import (
    TraceHistoryBoundary,
    TraceHistoryTranscript,
    TraceHttpAttempt,
    TraceHttpBody,
    TraceHttpCompleteness,
    TraceHttpEvidence,
    TraceMaskedEvidence,
    TraceModelCall,
    TraceModelEvidence,
    TraceModelIndex,
    TraceSseAvailability,
    TraceSseFramePage,
    TraceSseHeaders,
    TraceSseLane,
    TraceToolCall,
    TraceToolEvidence,
)
from pydantic import BaseModel, TypeAdapter

from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceTurn,
    ExportConversationTracesRequest,
    TraceContentAccess,
    TraceExportMode,
)
from control_plane_backend.conversation_traces.store import (
    ConversationTraceStore,
    TraceConversationReference,
    TraceEvidenceIndex,
    TraceExportState,
)

_MAX_TURNS = 1000
_STATE_LIMIT = _MAX_TURNS + 101
_MAX_FILES = 4096
_MAX_BYTES = 64 * 1024 * 1024
_CONVERSATIONS_AT_ONCE = 4
_EVIDENCE_INDEX_BATCH = 8
_HISTORY_TURNS = TypeAdapter(list[TraceHistoryBoundary])
_TRANSCRIPT = TypeAdapter(TraceHistoryTranscript)
_HTTP = TypeAdapter(TraceHttpEvidence)
_SSE_PAGE = TypeAdapter(TraceSseFramePage)
_SSE_HEADERS = TypeAdapter(TraceSseHeaders)
_MODEL = TypeAdapter(TraceModelEvidence)
_TOOL = TypeAdapter(TraceToolEvidence)
_MASKED = TypeAdapter(TraceMaskedEvidence)
_JSON_OBJECT = TypeAdapter(dict[str, object])

_T = TypeVar("_T")
_Value = TypeVar("_Value", contravariant=True)
EvidenceStatus = Literal["available", "partial", "masked", "unavailable", "empty"]
EvidenceKind = Literal["history", "http", "sse", "model", "tool"]


class ReadRuntimeTrace(Protocol):
    async def __call__(
        self,
        reference: TraceConversationReference,
        path: str,
        decoder: TypeAdapter[_T],
        *,
        params: dict[str, str | int] | None = None,
    ) -> _T:
        raise NotImplementedError


class TraceExportArtifact(BaseModel):
    status: EvidenceStatus
    files: list[str]
    metadata: (
        TraceHttpAttempt | TraceSseLane | TraceModelCall | TraceToolCall | None
    ) = None
    lane: Literal["provider", "outgoing"] | None = None
    segment: int | None = None
    headers_status: EvidenceStatus | None = None
    provider_body_ref: str | None = None


class TraceExportEvidence(BaseModel):
    status: EvidenceStatus
    files: list[str]
    items: list[TraceExportArtifact]


class TraceExportTurn(ConversationTraceTurn):
    evidence: dict[EvidenceKind, TraceExportEvidence]


class TraceExportConversation(BaseModel):
    session_id: str
    team_id: str
    agent_display_name: str
    title: str | None = None
    consent_cutoff: TraceHistoryBoundary | None
    history_status: EvidenceStatus


@dataclass
class TraceArchiveFiles:
    entries: list[tuple[str, bytes]] = field(default_factory=list)
    size: int = 0
    turns: int = 0
    version: int = 1

    def account_turns(self, count: int) -> None:
        self.turns += count
        if self.turns > _MAX_TURNS:
            raise HTTPException(413, "trace_export_too_large")

    def account(self, data: bytes) -> bytes:
        if self.size + len(data) > _MAX_BYTES:
            raise HTTPException(413, "trace_export_too_large")
        self.size += len(data)
        return data

    def add(self, path: str, data: bytes) -> str:
        """Keep immutable entries until the completed archive is authorized."""
        if len(self.entries) >= _MAX_FILES - 1:
            raise HTTPException(413, "trace_export_too_large")
        self.entries.append((path, self.account(data)))
        return path

    def zip_bytes(self, manifest: list[bytes]) -> bytes:
        """Compress off the event loop and return the finished portable file."""
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=3) as archive:
            for path, data in self.entries:
                archive.writestr(path, data)
            with archive.open("manifest.json", "w") as entry:
                for part in manifest:
                    entry.write(part)
        return buffer.getvalue()


async def _collect_together(*work: Coroutine[None, None, _T]) -> list[_T]:
    tasks = [asyncio.create_task(item) for item in work]
    try:
        return list(await asyncio.gather(*tasks))
    finally:
        if any(not task.done() for task in tasks):
            for task in tasks:
                task.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(*tasks, return_exceptions=True)


async def _read_available(
    read: ReadRuntimeTrace,
    reference: TraceConversationReference,
    path: str,
    decoder: TypeAdapter[_T],
    *,
    params: dict[str, str | int] | None = None,
) -> tuple[_T | None, EvidenceStatus]:
    """Record individually inaccessible or missing runtime evidence in the manifest."""
    try:
        return await read(reference, path, decoder, params=params), "available"
    except HTTPException as exc:
        if exc.status_code == 403:
            return None, "masked"
        if exc.status_code in (404, 503):
            return None, "unavailable"
        raise


def _group(
    items: list[TraceExportArtifact], default: EvidenceStatus = "unavailable"
) -> TraceExportEvidence:
    """Describe indexed items and summarize incomplete evidence for one kind."""
    statuses: set[EvidenceStatus] = {item.status for item in items}
    status: EvidenceStatus = default
    if len(statuses) == 1:
        status = next(iter(statuses))
    elif statuses == {"available", "empty"}:
        status = "available"
    elif statuses:
        status = "partial"
    return TraceExportEvidence(
        status=status,
        items=items,
        files=[path for item in items for path in item.files],
    )


def _opaque_bytes(data: str) -> bytes:
    """Restore exact recorded bytes from the runtime's typed base64 envelope."""
    try:
        return b64decode(data, validate=True)
    except (ValueError, Base64Error) as exc:
        raise HTTPException(503, "trace_export_evidence_invalid") from exc


async def _history(
    read: ReadRuntimeTrace,
    reference: TraceConversationReference,
    turn: ConversationTraceTurn,
    prefix: str,
    files: TraceArchiveFiles,
    *,
    include_content: bool,
) -> TraceExportEvidence:
    """Read all consent-covered transcript pages while preserving unavailable history."""
    status: EvidenceStatus = (
        "masked"
        if turn.access == TraceContentAccess.MASKED
        else "available"
        if turn.retained_cutoff is not None
        else "unavailable"
    )
    entries: list[str] = []
    if include_content and status != "masked" and turn.exchange_id not in {".", ".."}:
        path = f"trace-history-turns/{quote(turn.exchange_id, safe='')}"
        after = -1
        while True:
            value, status = await _read_available(
                read,
                reference,
                path,
                _TRANSCRIPT,
                params={"after_rank": after, "limit": 50},
            )
            if value is None or not value.available:
                status = "partial" if entries else ("unavailable" if value else status)
                break
            entries.append(
                files.add(
                    f"{prefix}/history/{len(entries) + 1:04d}.json",
                    value.model_dump_json().encode(),
                )
            )
            if value.next_rank is None:
                status = "available" if value.messages or len(entries) > 1 else "empty"
                break
            if value.next_rank <= after:
                status = "partial"
                break
            after = value.next_rank
    return _group([TraceExportArtifact(status=status, files=entries)])


@dataclass
class _TurnExport:
    store: ConversationTraceStore
    read: ReadRuntimeTrace
    reference: TraceConversationReference
    turn: ConversationTraceTurn
    prefix: str
    files: TraceArchiveFiles
    include_content: bool
    include_masked: bool

    async def _masked(
        self, kind: str, path: str, **params: str | int
    ) -> tuple[list[str], EvidenceStatus, int | None]:
        exchange = quote(self.turn.exchange_id, safe="")
        value, status = await _read_available(
            self.read,
            self.reference,
            f"trace-masked/{exchange}/{kind}",
            _MASKED,
            params=params,
        )
        if value is None:
            return [], status, None
        self.files.version = max(3, self.files.version)
        payloads: dict[str, object] = {
            key: document.data
            for key, document in value.documents.items()
            if not document.unavailable
        }
        annotations: dict[str, object] = {
            key: {
                "annotations": [item.model_dump() for item in document.annotations],
                "unavailable": document.unavailable,
            }
            for key, document in value.documents.items()
            if document.annotations or document.unavailable
        }
        entries = []
        if payloads:
            entries.append(
                self.files.add(f"{path}.masked.json", _JSON_OBJECT.dump_json(payloads))
            )
        if annotations:
            entries.append(
                self.files.add(
                    f"{path}.annotations.json", _JSON_OBJECT.dump_json(annotations)
                )
            )
        status = (
            "unavailable"
            if not payloads
            else "partial"
            if any(document.unavailable for document in value.documents.values())
            else "masked"
        )
        return entries, status, value.next_rank

    async def _collect_history(self) -> TraceExportEvidence:
        if not self.include_masked or (
            self.include_content and self.turn.access != TraceContentAccess.MASKED
        ):
            return await _history(
                self.read,
                self.reference,
                self.turn,
                self.prefix,
                self.files,
                include_content=self.include_content,
            )
        entries: list[str] = []
        statuses: set[EvidenceStatus] = set()
        after, page = -1, 1
        while True:
            paths, status, next_rank = await self._masked(
                "history", f"{self.prefix}/history/{page:04d}", after_rank=after
            )
            entries.extend(paths)
            statuses.add(status)
            if next_rank is None:
                break
            if next_rank <= after:
                status = "partial"
                break
            after, page = next_rank, page + 1
        return _group(
            [
                TraceExportArtifact(
                    status=status if len(statuses) == 1 else "partial", files=entries
                )
            ]
        )

    def _status(self, rank: int | None, available: EvidenceStatus) -> EvidenceStatus:
        """Check the artifact's observed rank as well as the turn's starting rank."""
        if available in ("unavailable", "empty"):
            return available
        if self.turn.access == TraceContentAccess.LOCAL:
            return available
        grant = self.reference.consent
        if (
            self.turn.access == TraceContentAccess.MASKED
            or grant is None
            or rank is None
            or rank > grant.cutoff.last_rank
        ):
            return "masked"
        return available

    async def _artifact(
        self,
        kind: EvidenceKind,
        metadata: TraceHttpAttempt | TraceSseLane | TraceModelCall | TraceToolCall,
        decoder: TypeAdapter[_T],
        status: EvidenceStatus,
        write: "_ArtifactWriter[_T]",
        *,
        lane: Literal["provider", "outgoing"] | None = None,
        segment: int | None = None,
        runtime_kind: str | None = None,
    ) -> TraceExportArtifact:
        """Resolve one protected artifact through the corresponding Runtime API."""
        entries: list[str] = []
        if (
            self.include_content
            and status in ("available", "partial")
            and self.turn.exchange_id not in {".", ".."}
        ):
            exchange = quote(self.turn.exchange_id, safe="")
            value, read_status = await _read_available(
                self.read,
                self.reference,
                f"trace-{runtime_kind or kind}/{exchange}/{metadata.ref}",
                decoder,
            )
            if value is None:
                status = read_status
            else:
                entries = await write(f"{self.prefix}/{kind}/{metadata.ref}", value)
        if (
            self.include_masked
            and status in ("available", "partial", "masked")
            and not entries
            and self.turn.exchange_id not in {".", ".."}
        ):
            entries, status, _ = await self._masked(
                runtime_kind or kind,
                f"{self.prefix}/{kind}/{metadata.ref}"
                + ("-headers" if runtime_kind == "sse-headers" else ""),
                ref=metadata.ref,
            )
            if (
                status == "masked"
                and not isinstance(metadata, TraceSseLane)
                and metadata.completeness == TraceHttpCompleteness.PARTIAL
            ):
                status = "partial"
        return TraceExportArtifact(
            status=status, files=entries, metadata=metadata, lane=lane, segment=segment
        )

    async def _write_http_body(
        self,
        path: str,
        side: Literal["request", "response"],
        first: TraceHttpBody,
    ) -> tuple[list[dict[str, str | int]], bool]:
        ref = path.rsplit("/", 1)[-1]
        exchange = quote(self.turn.exchange_id, safe="")
        endpoint = f"trace-http/{exchange}/{ref}"
        parts: list[dict[str, str | int]] = []
        body = first
        expected = 0
        complete = first.complete
        while True:
            offset = body.offset if body.offset is not None else expected
            data = _opaque_bytes(body.data)
            if data:
                name = f"{path}-{side}-{offset}.bin"
                parts.append({"file": self.files.add(name, data), "offset": offset})
            complete = complete and body.complete and offset == expected
            expected = offset + len(data)
            following = body.next_offset
            if following is None:
                return parts, complete and (
                    first.total_bytes is None or expected == first.total_bytes
                )
            if following <= offset or following < expected:
                raise HTTPException(503, "trace_export_evidence_invalid")
            exchange_body, _ = await _read_available(
                self.read,
                self.reference,
                endpoint,
                _HTTP,
                params={f"{side}_offset": following},
            )
            next_body = (
                (
                    exchange_body.request_body
                    if side == "request"
                    else exchange_body.response_body
                )
                if exchange_body is not None
                else None
            )
            if next_body is None:
                return parts, False
            if next_body.offset is None or next_body.offset < following:
                raise HTTPException(503, "trace_export_evidence_invalid")
            body = next_body

    async def _write_sse_pages(
        self,
        lane: TraceSseLane,
        status: EvidenceStatus,
        kind: Literal["outgoing", "provider"],
        segment: int,
    ) -> TraceExportArtifact:
        if lane.page_starts_ms:
            self.files.version = max(2, self.files.version)
        entries = []
        body_ref = None
        if self.include_content and status in ("available", "partial"):
            exchange = quote(self.turn.exchange_id, safe="")
            for page in range(len(lane.page_starts_ms)):
                value, page_status = await _read_available(
                    self.read,
                    self.reference,
                    f"trace-sse-frames/{exchange}/{lane.ref}/{page}",
                    _SSE_PAGE,
                    params={"outgoing_payload": "true"} if kind == "outgoing" else None,
                )
                if value is None:
                    status = "partial" if entries else page_status
                    break
                stem = f"{self.prefix}/sse/{lane.ref}-frames-{page}"
                entries.append(
                    self.files.add(
                        f"{stem}.json",
                        value.model_dump_json(exclude={"raw_data"}).encode(),
                    )
                )
                if value.raw_data:
                    entries.append(
                        self.files.add(f"{stem}.bin", _opaque_bytes(value.raw_data))
                    )
                if not value.frames or (
                    kind == "outgoing"
                    and any(frame.offset is None for frame in value.frames)
                ):
                    status = "partial"
            if kind == "provider" and entries:
                body_ref = lane.ref
        if (
            self.include_masked
            and status in ("available", "partial", "masked")
            and not entries
        ):
            statuses: set[EvidenceStatus] = set()
            for page in range(len(lane.page_starts_ms)):
                paths, page_status, _ = await self._masked(
                    "sse",
                    f"{self.prefix}/sse/{lane.ref}-frames-{page}",
                    ref=lane.ref,
                    index=page,
                    batch="true",
                )
                entries.extend(paths)
                statuses.add(page_status)
            if statuses:
                status = statuses.pop() if len(statuses) == 1 else "partial"
                if (
                    status == "masked"
                    and lane.availability == TraceSseAvailability.PARTIAL
                ):
                    status = "partial"
        return TraceExportArtifact(
            status=status,
            files=entries,
            metadata=lane,
            lane=kind,
            segment=segment,
            provider_body_ref=body_ref,
        )

    async def collect(self, index: TraceEvidenceIndex) -> TraceExportTurn:
        """Read metadata for every turn and bytes only for its authorized evidence."""
        turn = self.turn
        reference = self.reference

        async def write_http(path: str, value: TraceHttpEvidence) -> list[str]:
            envelope = value.model_dump(exclude={"request_body", "response_body"})
            self.files.version = max(2, self.files.version)
            entries = []
            bodies: tuple[
                tuple[Literal["request", "response"], TraceHttpBody | None], ...
            ] = (
                ("request", value.request_body),
                ("response", value.response_body),
            )
            for side, body in bodies:
                if body is None:
                    continue
                parts, complete = await self._write_http_body(path, side, body)
                entries.extend(part["file"] for part in parts)
                envelope[f"{side}_body"] = {
                    "parts": parts,
                    "total_bytes": body.total_bytes,
                    "decoded": body.decoded,
                    "complete": complete,
                }
            return [
                self.files.add(f"{path}.json", _JSON_OBJECT.dump_json(envelope)),
                *entries,
            ]

        async def write_headers(path: str, value: TraceSseHeaders) -> list[str]:
            return [
                self.files.add(f"{path}-headers.json", value.model_dump_json().encode())
            ]

        async def write_json(path: str, value: BaseModel) -> list[str]:
            return [self.files.add(f"{path}.json", value.model_dump_json().encode())]

        async def collect_http() -> TraceExportEvidence:
            http = [
                await self._artifact(
                    "http",
                    item,
                    _HTTP,
                    self._status(item.observed_through_rank, _state(item.completeness)),
                    write_http,
                )
                for item in index.http
            ]
            return _group(http)

        async def collect_sse() -> TraceExportEvidence:
            sse = []
            for ordinal, segment in enumerate(index.sse, 1):
                pairs: list[tuple[Literal["outgoing", "provider"], TraceSseLane]] = []
                if segment.outgoing is not None:
                    pairs.append(("outgoing", segment.outgoing))
                pairs.extend(("provider", lane) for lane in segment.provider)
                for kind, lane in pairs:
                    status = _SSE_STATES[lane.availability]
                    artifact = await self._write_sse_pages(
                        lane,
                        self._status(
                            segment.observed_through_rank,
                            "unavailable"
                            if not lane.page_starts_ms and status != "empty"
                            else status,
                        ),
                        kind,
                        ordinal,
                    )
                    if lane.headers_available:
                        headers = await self._artifact(
                            "sse",
                            lane,
                            _SSE_HEADERS,
                            self._status(segment.observed_through_rank, "available"),
                            write_headers,
                            runtime_kind="sse-headers",
                        )
                        artifact.headers_status = headers.status
                        artifact.files.extend(headers.files)
                        if artifact.status == "empty":
                            artifact.status = headers.status
                        elif (
                            artifact.status == "unavailable"
                            and headers.status == "available"
                        ):
                            artifact.status = "partial"
                        elif (
                            artifact.status == "available"
                            and headers.status != "available"
                        ):
                            artifact.status = "partial"
                    elif lane.headers_ms is not None:
                        artifact.headers_status = "unavailable"
                    sse.append(artifact)
            return _group(sse)

        async def collect_model() -> TraceExportEvidence:
            model = []
            for item in index.model:

                async def write_model(
                    path: str, value: TraceModelEvidence, call: TraceModelIndex = item
                ) -> list[str]:
                    value.origins = await self.store.model_origins(
                        reference.session_id,
                        turn.exchange_id,
                        call,
                        cutoff_rank=reference.consent.cutoff.last_rank
                        if reference.consent is not None
                        and turn.access != TraceContentAccess.LOCAL
                        else None,
                    )
                    return await write_json(path, value)

                model.append(
                    await self._artifact(
                        "model",
                        TraceModelCall.model_validate(item.model_dump()),
                        _MODEL,
                        self._status(
                            item.observed_through_rank, _state(item.completeness)
                        ),
                        write_model,
                    )
                )
            return _group(model)

        async def collect_tool() -> TraceExportEvidence:
            tool = [
                await self._artifact(
                    "tool",
                    item,
                    _TOOL,
                    self._status(item.observed_through_rank, _state(item.completeness)),
                    write_json,
                )
                for item in index.tool
            ]
            return _group(tool)

        history, http, sse, model, tool = await _collect_together(
            self._collect_history(),
            collect_http(),
            collect_sse(),
            collect_model(),
            collect_tool(),
        )
        return TraceExportTurn(
            **turn.model_dump(),
            evidence={
                "history": history,
                "http": http,
                "sse": sse,
                "model": model,
                "tool": tool,
            },
        )


class _ArtifactWriter(Protocol[_Value]):
    async def __call__(self, path: str, value: _Value) -> list[str]:
        raise NotImplementedError


_SSE_STATES: dict[TraceSseAvailability, EvidenceStatus] = {
    TraceSseAvailability.CAPTURED: "available",
    TraceSseAvailability.PARTIAL: "partial",
    TraceSseAvailability.EMPTY: "empty",
    TraceSseAvailability.UNAVAILABLE: "unavailable",
}


def _state(value: TraceHttpCompleteness) -> EvidenceStatus:
    """Map a complete artifact to the manifest's availability vocabulary."""
    return (
        "available"
        if value == TraceHttpCompleteness.COMPLETE
        else "partial"
        if value == TraceHttpCompleteness.PARTIAL
        else "unavailable"
    )


@dataclass
class _ConversationExport:
    store: ConversationTraceStore
    read: ReadRuntimeTrace
    files: TraceArchiveFiles
    include_content: bool
    include_masked: bool
    local_request: bool

    async def collect(self, number: int, session_id: str) -> list[bytes]:
        reference = await self.store.reference(session_id)
        if reference is None or not reference.visible:
            raise HTTPException(409, "trace_export_changed")
        local = self.local_request and not reference.retained_after_delete
        account = self.files.account
        manifest: list[bytes] = []
        after = None
        turn_index = 0
        history_states: set[EvidenceStatus] = set()
        while True:
            params: dict[str, int | str] = {"limit": 101}
            if after is not None:
                params.update(after_rank=after[0], after_exchange=after[1])
            history, status = await _read_available(
                self.read,
                reference,
                "trace-history-turns",
                _HISTORY_TURNS,
                params=params,
            )
            history_states.add(status)
            page = await self.store.conversation_page(
                reference,
                limit=100,
                after=after,
                retained_turns=history if history is not None else [],
                local_content_access=local,
            )
            self.files.account_turns(len(page.turns))
            for batch in batched(page.turns, _EVIDENCE_INDEX_BATCH):
                indexes = await self.store.export_evidence_indexes(
                    session_id, [turn.exchange_id for turn in batch]
                )
                for turn in batch:
                    if turn_index:
                        manifest.append(account(b","))
                    turn_index += 1
                    exporter = _TurnExport(
                        self.store,
                        self.read,
                        reference,
                        turn,
                        f"conversations/{number:03d}/turns/{turn_index:04d}",
                        self.files,
                        self.include_content,
                        self.include_masked,
                    )
                    exported_turn = await exporter.collect(
                        indexes.get(turn.exchange_id)
                        or TraceEvidenceIndex([], [], [], [])
                    )
                    manifest.append(
                        account(
                            exported_turn.model_dump_json(exclude_none=True).encode()
                        )
                    )
            if page.next_cursor is None:
                break
            rank, exchange = page.next_cursor.split("|", 1)
            after = (int(rank), exchange)
        result = TraceExportConversation(
            session_id=session_id,
            team_id=reference.team_id,
            agent_display_name=reference.agent_display_name,
            title=reference.title
            if self.include_content and (local or reference.title_authorized)
            else None,
            consent_cutoff=reference.consent.cutoff if reference.consent else None,
            history_status=(
                next(iter(history_states)) if len(history_states) == 1 else "partial"
            ),
        )
        return [
            account(
                result.model_dump_json(exclude_none=True).encode()[:-1] + b',"turns":['
            ),
            *manifest,
            account(b"]}"),
        ]


async def build_trace_archive(
    store: ConversationTraceStore,
    request: ExportConversationTracesRequest,
    read: ReadRuntimeTrace,
    *,
    local_request: bool,
) -> tuple[bytes, list[TraceExportState]]:
    """Produce a ZIP plus the visibility snapshot to revalidate before delivery."""
    session_ids = list(dict.fromkeys(request.session_ids))
    state = await trace_export_state(store, session_ids)
    if {item.session_id for item in state} != set(session_ids):
        raise HTTPException(404, "conversation_trace_not_found")
    files = TraceArchiveFiles()
    manifest = []
    exporter = _ConversationExport(
        store,
        read,
        files,
        request.mode == TraceExportMode.SHARED_CONTENT,
        request.mode != TraceExportMode.METADATA_ONLY,
        local_request,
    )
    for batch in batched(enumerate(session_ids, 1), _CONVERSATIONS_AT_ONCE):
        pieces = await _collect_together(
            *(exporter.collect(number, session_id) for number, session_id in batch)
        )
        for conversation in pieces:
            if manifest:
                manifest.append(files.account(b","))
            manifest.extend(conversation)
    header = _JSON_OBJECT.dump_json(
        {"version": files.version, "mode": request.mode.value}
    )
    manifest.insert(0, files.account(header[:-1] + b',"conversations":['))
    manifest.append(files.account(b"]}"))
    return await anyio.to_thread.run_sync(files.zip_bytes, manifest), state


async def trace_export_state(
    store: ConversationTraceStore, session_ids: list[str]
) -> list[TraceExportState]:
    """Read at most one extra indexed row beyond the limits for a portable bundle."""
    state = await store.export_state(session_ids, limit=_STATE_LIMIT)
    if (
        len(state) >= _STATE_LIMIT
        or sum(item.capture_id is not None for item in state) > _MAX_TURNS
    ):
        raise HTTPException(413, "trace_export_too_large")
    return state
