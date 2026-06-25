from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from control_plane_backend.self_test import corpus
from control_plane_backend.self_test.knowledge_flow_client import (
    KnowledgeFlowClient,
    KnowledgeFlowError,
)
from control_plane_backend.self_test.models import (
    RunState,
    SelfTestEvent,
    SelfTestRun,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)

# Async ingestion (kf-worker) means the positive query is eventually consistent.
_QUERY_RETRIES = 8
_QUERY_RETRY_DELAY_S = 2.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _RunContext:
    """In-memory live state for one campaign run (single-replica prototype)."""

    run: SelfTestRun
    queue: asyncio.Queue[SelfTestEvent | None] = field(default_factory=asyncio.Queue)
    seq: int = 0
    # Resources created during the run, shared across steps.
    library_alpha_id: str | None = None
    library_beta_id: str | None = None
    doc_alpha_uid: str | None = None
    doc_beta_uid: str | None = None


# Module-level registry so SSE/status requests can find a run started elsewhere.
_RUNS: dict[str, _RunContext] = {}


class SelfTestEngine:
    """Runs the ordered validation campaign and streams step transitions.

    Setup and query steps may fail; teardown steps ALWAYS run so the synthetic
    team never leaks fixture data — that is also how we validate delete.
    """

    def __init__(
        self,
        *,
        knowledge_flow_base_url: str,
        team_id: str,
        keep_corpus: bool = False,
    ) -> None:
        self._base_url = knowledge_flow_base_url
        self._team_id = team_id
        self._keep_corpus = keep_corpus
        # The caller must be able to READ the corpus it creates. "personal" scopes
        # it to the triggering admin (always readable); a real team only works if
        # the caller is a member of it. owner_filter must match for search to see
        # the tags (see ADMIN-SELF-TEST-HARNESS-RFC §9).
        self._is_personal = team_id in ("", "personal")
        self._owner_filter = "personal" if self._is_personal else "team"
        self._search_team_id = None if self._is_personal else team_id

    def start(self, authorization: str | None) -> str:
        run_id = uuid4().hex
        run = SelfTestRun(
            run_id=run_id,
            team_id=self._team_id,
            started_at=_now(),
            steps=[
                StepResult(id=step_id, title=title) for step_id, title in _STEP_PLAN
            ],
        )
        ctx = _RunContext(run=run)
        _RUNS[run_id] = ctx
        asyncio.create_task(self._run_campaign(ctx, authorization))
        return run_id

    async def _run_campaign(self, ctx: _RunContext, authorization: str | None) -> None:
        client = KnowledgeFlowClient(self._base_url, authorization)
        try:
            await self._run_setup_and_queries(ctx, client)
        except Exception:  # noqa: BLE001 — defensive: teardown must still run
            logger.exception("self-test campaign aborted before teardown")
        finally:
            await self._run_teardown(ctx, client)
            self._finalize(ctx)

    # ── setup + query steps (may fail) ───────────────────────────────────────

    async def _run_setup_and_queries(
        self, ctx: _RunContext, client: KnowledgeFlowClient
    ) -> None:
        a, b = corpus.LIBRARY_ALPHA, corpus.LIBRARY_BETA

        async def create_alpha() -> str:
            ctx.library_alpha_id = await client.create_library(
                name=a.name, description=a.description, team_id=self._team_id
            )
            return f"library {a.name} ({ctx.library_alpha_id})"

        async def create_beta() -> str:
            ctx.library_beta_id = await client.create_library(
                name=b.name, description=b.description, team_id=self._team_id
            )
            return f"library {b.name} ({ctx.library_beta_id})"

        async def ingest_alpha() -> str:
            assert ctx.library_alpha_id
            ctx.doc_alpha_uid = await client.ingest_document(
                library_id=ctx.library_alpha_id,
                filename=a.document.filename,
                text=a.document.text,
            )
            return f"document {ctx.doc_alpha_uid}"

        async def ingest_beta() -> str:
            assert ctx.library_beta_id
            ctx.doc_beta_uid = await client.ingest_document(
                library_id=ctx.library_beta_id,
                filename=b.document.filename,
                text=b.document.text,
            )
            return f"document {ctx.doc_beta_uid}"

        async def query_positive() -> str:
            assert ctx.library_alpha_id
            # Ingestion is processed asynchronously by kf-worker, so the document
            # may not be vectorized the instant the ingest step returns. Poll the
            # search until the marker shows up (eventual consistency) before
            # declaring a miss.
            last_hits = 0
            for attempt in range(_QUERY_RETRIES):
                hits = await client.search(
                    question=corpus.PROBE_QUESTION,
                    library_id=ctx.library_alpha_id,
                    owner_filter=self._owner_filter,
                    team_id=self._search_team_id,
                )
                last_hits = len(hits)
                if _marker_present(hits):
                    return f"marker retrieved from alpha ({last_hits} hits, attempt {attempt + 1})"
                await asyncio.sleep(_QUERY_RETRY_DELAY_S)
            # Diagnostic fallback: search the SAME document by uid (no tag filter).
            # If the marker shows up this way, the chunk is indexed+retrievable and
            # the library scoping (chunk metadata.tag_ids) is the culprit; if not,
            # the chunk isn't retrievable at all.
            by_doc = await client.search(
                question=corpus.PROBE_QUESTION,
                document_uid=ctx.doc_alpha_uid,
                owner_filter=self._owner_filter,
                team_id=self._search_team_id,
            )
            doc_diag = (
                f"by-document-uid fallback: {len(by_doc)} hits, "
                f"marker={'present' if _marker_present(by_doc) else 'absent'}"
            )
            raise KnowledgeFlowError(
                f"marker '{corpus.MARKER_PHRASE}' not retrieved from alpha after "
                f"{_QUERY_RETRIES} attempts ({last_hits} hits) "
                f"[scope: owner_filter={self._owner_filter}, team_id={self._search_team_id}, "
                f"library={ctx.library_alpha_id}, doc={ctx.doc_alpha_uid}] — {doc_diag}"
            )

        async def query_isolation() -> str:
            assert ctx.library_beta_id
            hits = await client.search(
                question=corpus.PROBE_QUESTION,
                library_id=ctx.library_beta_id,
                owner_filter=self._owner_filter,
                team_id=self._search_team_id,
            )
            if _marker_present(hits):
                raise KnowledgeFlowError(
                    f"marker '{corpus.MARKER_PHRASE}' leaked into beta scope"
                )
            return f"marker correctly absent from beta ({len(hits)} hits)"

        await self._step(ctx, "create-library-alpha", create_alpha)
        await self._step(ctx, "create-library-beta", create_beta)
        await self._step(ctx, "ingest-doc-alpha", ingest_alpha)
        await self._step(ctx, "ingest-doc-beta", ingest_beta)
        await self._step(ctx, "query-scope-positive", query_positive)
        await self._step(ctx, "query-scope-isolation", query_isolation)

    # ── teardown steps (always run; skip if nothing to delete) ────────────────

    async def _run_teardown(
        self, ctx: _RunContext, client: KnowledgeFlowClient
    ) -> None:
        if self._keep_corpus:
            # Debug mode: leave the corpus in place for manual inspection.
            for step_id in (
                "delete-doc-alpha",
                "delete-doc-beta",
                "delete-library-alpha",
                "delete-library-beta",
            ):
                await self._step(ctx, step_id, _keep_corpus_skip)
            return

        async def delete_doc_alpha() -> str:
            if not ctx.doc_alpha_uid:
                raise _Skip("no alpha document was created")
            await client.delete_document(ctx.doc_alpha_uid)
            return f"deleted {ctx.doc_alpha_uid}"

        async def delete_doc_beta() -> str:
            if not ctx.doc_beta_uid:
                raise _Skip("no beta document was created")
            await client.delete_document(ctx.doc_beta_uid)
            return f"deleted {ctx.doc_beta_uid}"

        async def delete_lib_alpha() -> str:
            if not ctx.library_alpha_id:
                raise _Skip("no alpha library was created")
            await client.delete_library(ctx.library_alpha_id)
            return f"deleted {ctx.library_alpha_id}"

        async def delete_lib_beta() -> str:
            if not ctx.library_beta_id:
                raise _Skip("no beta library was created")
            await client.delete_library(ctx.library_beta_id)
            return f"deleted {ctx.library_beta_id}"

        await self._step(ctx, "delete-doc-alpha", delete_doc_alpha)
        await self._step(ctx, "delete-doc-beta", delete_doc_beta)
        await self._step(ctx, "delete-library-alpha", delete_lib_alpha)
        await self._step(ctx, "delete-library-beta", delete_lib_beta)

    # ── step runner + event emission ─────────────────────────────────────────

    async def _step(
        self,
        ctx: _RunContext,
        step_id: str,
        action: Callable[[], Awaitable[str]],
    ) -> None:
        step = _find_step(ctx.run, step_id)
        step.status = StepStatus.running
        step.started_at = _now()
        await self._emit(ctx, step)
        try:
            detail = await action()
            step.status = StepStatus.passed
            step.detail = detail
        except _Skip as skip:
            step.status = StepStatus.skipped
            step.detail = str(skip)
        except Exception as exc:  # noqa: BLE001 — any failure is a step failure
            step.status = StepStatus.failed
            step.error = str(exc)
            logger.warning("self-test step %s failed: %s", step_id, exc)
        finally:
            step.finished_at = _now()
            if step.started_at:
                step.duration_ms = int(
                    (step.finished_at - step.started_at).total_seconds() * 1000
                )
            await self._emit(ctx, step)

    async def _emit(self, ctx: _RunContext, current: StepResult) -> None:
        ctx.seq += 1
        event = SelfTestEvent(
            run_id=ctx.run.run_id,
            state=ctx.run.state,
            seq=ctx.seq,
            progress=ctx.run.progress,
            step=current.title,
            steps=list(ctx.run.steps),
        )
        await ctx.queue.put(event)

    def _finalize(self, ctx: _RunContext) -> None:
        any_failed = any(s.status == StepStatus.failed for s in ctx.run.steps)
        ctx.run.state = RunState.failed if any_failed else RunState.passed
        ctx.run.finished_at = _now()
        ctx.queue.put_nowait(None)  # sentinel: closes the SSE stream


class _Skip(Exception):
    """A step that has nothing to do (not a failure)."""


async def _keep_corpus_skip() -> str:
    raise _Skip("kept for inspection (self_test.keep_corpus=true)")


_STEP_PLAN: list[tuple[str, str]] = [
    ("create-library-alpha", "Create library ALPHA"),
    ("create-library-beta", "Create library BETA"),
    ("ingest-doc-alpha", "Ingest document into ALPHA"),
    ("ingest-doc-beta", "Ingest document into BETA"),
    ("query-scope-positive", "Query ALPHA — marker must be found"),
    ("query-scope-isolation", "Query BETA — marker must be absent"),
    ("delete-doc-alpha", "Delete ALPHA document"),
    ("delete-doc-beta", "Delete BETA document"),
    ("delete-library-alpha", "Delete library ALPHA"),
    ("delete-library-beta", "Delete library BETA"),
]


def _find_step(run: SelfTestRun, step_id: str) -> StepResult:
    for step in run.steps:
        if step.id == step_id:
            return step
    raise KeyError(step_id)


def _marker_present(hits: list[dict]) -> bool:
    needle = corpus.MARKER_PHRASE.lower()
    return any(needle in str(hit.get("content", "")).lower() for hit in hits)


def get_run(run_id: str) -> SelfTestRun | None:
    ctx = _RUNS.get(run_id)
    return ctx.run if ctx else None


def get_queue(run_id: str) -> asyncio.Queue[SelfTestEvent | None] | None:
    ctx = _RUNS.get(run_id)
    return ctx.queue if ctx else None
