# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Assemble a bounded trace ZIP in memory from the authenticated runtime reads."""

from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal, Protocol, TypeVar
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

import anyio
from fastapi import HTTPException
from fred_core.conversation_trace import (
    TraceHistoryBoundary,
    TraceHistoryTranscript,
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceHttpEvidence,
    TraceModelCall,
    TraceModelEvidence,
    TraceModelIndex,
    TraceSseAvailability,
    TraceSseFrame,
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
    TraceExportState,
)

_MAX_TURNS = 1000
_STATE_LIMIT = _MAX_TURNS + 101
_MAX_FILES = 4096
_MAX_BYTES = 64 * 1024 * 1024
_HISTORY_TURNS = TypeAdapter(list[TraceHistoryBoundary])
_TRANSCRIPT = TypeAdapter(TraceHistoryTranscript)
_HTTP = TypeAdapter(TraceHttpEvidence)
_SSE = TypeAdapter(TraceSseFrame)
_SSE_HEADERS = TypeAdapter(TraceSseHeaders)
_MODEL = TypeAdapter(TraceModelEvidence)
_TOOL = TypeAdapter(TraceToolEvidence)
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
    ) -> _T: ...


class TraceExportArtifact(BaseModel):
    status: EvidenceStatus
    files: list[str]
    metadata: (
        TraceHttpAttempt | TraceSseLane | TraceModelCall | TraceToolCall | None
    ) = None
    lane: Literal["provider", "outgoing"] | None = None
    segment: int | None = None
    headers_status: EvidenceStatus | None = None


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


@dataclass
class TraceArchiveFiles:
    entries: list[tuple[str, bytes]] = field(default_factory=list)
    manifest: BytesIO = field(default_factory=BytesIO)
    size: int = 0

    def add(self, path: str, data: bytes) -> str:
        """Keep immutable entries until the completed archive is authorized."""
        if self.size + len(data) > _MAX_BYTES or len(self.entries) >= _MAX_FILES - 1:
            raise HTTPException(413, "trace_export_too_large")
        self.size += len(data)
        self.entries.append((path, data))
        return path

    def append_manifest(self, data: bytes) -> None:
        """Account for metadata as it arrives, including turns without saved payloads."""
        if self.size + len(data) > _MAX_BYTES:
            raise HTTPException(413, "trace_export_too_large")
        self.size += len(data)
        self.manifest.write(data)

    def zip_bytes(self) -> bytes:
        """Compress off the event loop and return the finished portable file."""
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=3) as archive:
            for path, data in self.entries:
                archive.writestr(path, data)
            archive.writestr("manifest.json", self.manifest.getvalue())
        return buffer.getvalue()


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


def _http_files(
    files: TraceArchiveFiles, stem: str, value: TraceHttpEvidence
) -> list[str]:
    """Put headers and byte-preserving bodies in discoverable companion entries."""
    envelope = value.model_dump(exclude={"request_body", "response_body"})
    output = []
    for side, data in (
        ("request", value.request_body),
        ("response", value.response_body),
    ):
        if data is not None:
            path = files.add(f"{stem}-{side}.bin", _opaque_bytes(data.data))
            output.append(path)
            envelope[f"{side}_body"] = {"file": path, "complete": data.complete}
    return [files.add(f"{stem}.json", _JSON_OBJECT.dump_json(envelope)), *output]


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
        return TraceExportArtifact(
            status=status, files=entries, metadata=metadata, lane=lane, segment=segment
        )

    async def collect(self) -> TraceExportTurn:
        """Read metadata for every turn and bytes only for its authorized evidence."""
        turn = self.turn
        reference = self.reference
        index = await self.store.export_evidence_index(
            reference.session_id, turn.exchange_id
        )
        history = await _history(
            self.read,
            reference,
            turn,
            self.prefix,
            self.files,
            include_content=self.include_content,
        )

        async def write_http(path: str, value: TraceHttpEvidence) -> list[str]:
            return _http_files(self.files, path, value)

        async def write_sse(path: str, value: TraceSseFrame) -> list[str]:
            return [self.files.add(f"{path}.bin", _opaque_bytes(value.data))]

        async def write_headers(path: str, value: TraceSseHeaders) -> list[str]:
            return [
                self.files.add(f"{path}-headers.json", value.model_dump_json().encode())
            ]

        async def write_json(path: str, value: BaseModel) -> list[str]:
            return [self.files.add(f"{path}.json", value.model_dump_json().encode())]

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
        sse = []
        for ordinal, segment in enumerate(index.sse, 1):
            pairs: list[tuple[Literal["outgoing", "provider"], TraceSseLane]] = []
            if segment.outgoing is not None:
                pairs.append(("outgoing", segment.outgoing))
            pairs.extend(("provider", lane) for lane in segment.provider)
            for kind, lane in pairs:
                status = _SSE_STATES[lane.availability]
                if not lane.raw_size and status in ("partial", "available"):
                    status = "unavailable"
                artifact = await self._artifact(
                    "sse",
                    lane,
                    _SSE,
                    self._status(segment.observed_through_rank, status),
                    write_sse,
                    lane=kind,
                    segment=ordinal,
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
                        artifact.status == "available" and headers.status != "available"
                    ):
                        artifact.status = "partial"
                elif lane.headers_ms is not None:
                    artifact.headers_status = "unavailable"
                sse.append(artifact)
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
                    self._status(item.observed_through_rank, _state(item.completeness)),
                    write_model,
                )
            )
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
        return TraceExportTurn(
            **turn.model_dump(),
            evidence={
                "history": history,
                "http": _group(http),
                "sse": _group(sse),
                "model": _group(model),
                "tool": _group(tool),
            },
        )


class _ArtifactWriter(Protocol[_Value]):
    async def __call__(self, path: str, value: _Value) -> list[str]: ...


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
    header = _JSON_OBJECT.dump_json({"version": 1, "mode": request.mode.value})
    files.append_manifest(header[:-1] + b',"conversations":[')
    remaining = _MAX_TURNS
    include_content = request.mode == TraceExportMode.SHARED_CONTENT
    for number, session_id in enumerate(session_ids, 1):
        reference = await store.reference(session_id)
        if reference is None or not reference.visible:
            raise HTTPException(409, "trace_export_changed")
        local = local_request and not reference.retained_after_delete
        result = TraceExportConversation(
            session_id=session_id,
            team_id=reference.team_id,
            agent_display_name=reference.agent_display_name,
            title=reference.title
            if include_content and (local or reference.title_authorized)
            else None,
            consent_cutoff=reference.consent.cutoff if reference.consent else None,
        )
        if number > 1:
            files.append_manifest(b",")
        files.append_manifest(
            result.model_dump_json(exclude_none=True).encode()[:-1] + b',"turns":['
        )
        after = None
        turn_index = 0
        while True:
            params: dict[str, int | str] = {"limit": 101}
            if after is not None:
                params.update(after_rank=after[0], after_exchange=after[1])
            history, _ = await _read_available(
                read, reference, "trace-history-turns", _HISTORY_TURNS, params=params
            )
            page = await store.conversation_page(
                reference,
                limit=100,
                after=after,
                retained_turns=history or [],
                local_content_access=local,
            )
            remaining -= len(page.turns)
            if remaining < 0:
                raise HTTPException(413, "trace_export_too_large")
            for turn in page.turns:
                if turn_index:
                    files.append_manifest(b",")
                turn_index += 1
                prefix = f"conversations/{number:03d}/turns/{turn_index:04d}"
                exported_turn = await _TurnExport(
                    store, read, reference, turn, prefix, files, include_content
                ).collect()
                files.append_manifest(
                    exported_turn.model_dump_json(exclude_none=True).encode()
                )
            if page.next_cursor is None:
                break
            rank, exchange = page.next_cursor.split("|", 1)
            after = (int(rank), exchange)
        files.append_manifest(b"]}")
    files.append_manifest(b"]}")
    return await anyio.to_thread.run_sync(files.zip_bytes), state


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
