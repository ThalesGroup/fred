"""Conversation erasure — single fan-out entry point (CTRLP-12, RFC §3.A).

`ConversationErasureService.erase_session` erases one conversation across every
store the control-plane owns and returns an auditable `ErasureReceipt`
(per store: count, ok, error).

A1 lifted the existing `delete_session` body — attachments (+ Knowledge Flow
artifacts) and session metadata — behind this service, unchanged, wrapped in a
receipt. A2 appends the two runtime stores: the LangGraph checkpoint and the
transcript (`session_history`), erased over HTTP against the runtime that served
the session (A0 decision §A0), mirroring the `_delete_knowledge_flow_attachment`
helper. A3 appends the KPI store: KPI events are an analytics aggregate, so its
rows are *anonymised* (identifiers nulled), not deleted (RFC §3.3).
"""

from __future__ import annotations

import asyncio

import httpx
from fred_core.common import TeamId
from pydantic import BaseModel, Field, computed_field

from control_plane_backend.product import service as product_service
from control_plane_backend.product.dependencies import ProductServiceDependencies

# Stable store identifiers used as receipt keys.
STORE_ATTACHMENTS = "attachments"
STORE_SESSION_METADATA = "session_metadata"
STORE_KPI = "kpi"
STORE_CHECKPOINT = "runtime_checkpoint"
STORE_HISTORY = "runtime_history"

# Per-runtime-call timeout, matching the Knowledge Flow cleanup helper.
_RUNTIME_TIMEOUT_SECONDS = 15.0


class StoreErasureResult(BaseModel):
    """Outcome of erasing one store for one conversation."""

    store: str
    deleted_count: int | None = None
    ok: bool
    error: str | None = None


class ErasureReceipt(BaseModel):
    """Auditable, per-store record of one conversation erasure (RFC §3.A)."""

    session_id: str
    stores: list[StoreErasureResult] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        """True when every touched store erased without error."""
        return all(result.ok for result in self.stores)


class ConversationErasureService:
    """Fan out conversation erasure over every store the control-plane owns.

    Each erased store contributes one `StoreErasureResult` to the returned
    `ErasureReceipt`. The `authorization` bearer is threaded through so
    cross-service cleanup (Knowledge Flow today; runtime history/checkpoint in
    A2) runs with the caller's identity.
    """

    def __init__(self, deps: ProductServiceDependencies) -> None:
        self._deps = deps

    async def erase_session(
        self,
        *,
        team_id: TeamId,
        session_id: str,
        user_id: str,
        authorization: str,
    ) -> ErasureReceipt:
        """Erase one conversation and return its receipt.

        It validates team + ownership, cleans each attachment's Knowledge Flow
        artifacts, removes the attachment rows, deletes the session metadata
        row, then erases the runtime checkpoint and transcript over HTTP —
        checkpoint first so the runtime's ownership check still sees the history
        (A0). Each store is isolated: one failure is recorded and the rest run.
        """
        deps = self._deps
        receipt = ErasureReceipt(session_id=session_id)

        session = await product_service._get_owned_session_record(
            deps=deps,
            team_id=team_id,
            session_id=session_id,
            user_id=user_id,
        )
        if session is None:
            # Unreachable today (`_get_owned_session_record` raises 404 on a
            # miss); kept so erase stays total — nothing to erase yields an
            # empty, ok receipt rather than an error.
            return receipt

        # --- attachments (+ Knowledge Flow artifacts) --------------------
        attachment_store = deps.get_session_attachment_store()
        attachments = await attachment_store.list_for_session(session_id)
        for attachment in attachments:
            await product_service._delete_knowledge_flow_attachment(
                deps=deps,
                authorization=authorization,
                document_uid=attachment.document_uid,
                storage_key=attachment.storage_key,
                session_id=session_id,
            )
        await attachment_store.delete_for_session(session_id)
        receipt.stores.append(
            StoreErasureResult(
                store=STORE_ATTACHMENTS,
                deleted_count=len(attachments),
                ok=True,
            )
        )

        # --- session metadata --------------------------------------------
        deleted = await deps.get_session_metadata_store().delete(
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
        )
        receipt.stores.append(
            StoreErasureResult(
                store=STORE_SESSION_METADATA,
                deleted_count=1 if deleted else 0,
                ok=True,
            )
        )

        # --- KPI (A3): anonymise, do NOT delete (RFC §3.3) ---------------
        # Runs before the runtime block below because it is independent of the
        # runtime resolution — an unresolved runtime must not skip KPI erasure.
        receipt.stores.append(await self._anonymise_kpi(session_id))

        # --- runtime checkpoint + history (A2) ---------------------------
        # The transcript and LangGraph checkpoint live on whichever runtime
        # served this session; resolve its server-side base_url from the
        # session's agent_instance_id (A0). An unresolved runtime is recorded,
        # never guessed.
        base_url, resolve_error = await self._resolve_runtime_base_url(
            team_id=team_id,
            agent_instance_id=session.agent_instance_id,
        )
        if base_url is None:
            for store in (STORE_CHECKPOINT, STORE_HISTORY):
                receipt.stores.append(
                    StoreErasureResult(store=store, ok=False, error=resolve_error)
                )
            return receipt

        # Checkpoint BEFORE history: the runtime confirms checkpoint ownership
        # via the history store, so deleting history first 403s the checkpoint
        # and leaks it (A0). Each call is isolated — one store's failure records
        # ok=false and continues, keeping the fan-out best-effort-complete.
        receipt.stores.append(
            await self._erase_runtime_checkpoint(base_url, session_id, authorization)
        )
        receipt.stores.append(
            await self._erase_runtime_history(base_url, session_id, authorization)
        )

        return receipt

    async def _resolve_runtime_base_url(
        self,
        *,
        team_id: TeamId,
        agent_instance_id: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve the server-side runtime `base_url` for a session's runtime.

        Returns `(base_url, None)` on success, or `(None, error)` when the
        runtime cannot be resolved — no `agent_instance_id`, an unknown
        instance, or a disabled/missing runtime source. Callers record the
        error rather than guessing a runtime (A0).
        """
        if agent_instance_id is None:
            return None, "unresolved runtime: session has no agent_instance_id"

        instance = await self._deps.get_agent_instance_store().get_for_team(
            agent_instance_id, team_id
        )
        if instance is None:
            return None, (
                f"unresolved runtime: agent instance {agent_instance_id!r} "
                "not found for team"
            )

        source = next(
            (
                s
                for s in self._deps.configuration.platform.runtime_catalog_sources
                if s.runtime_id == instance.source_runtime_id and s.enabled
            ),
            None,
        )
        if source is None:
            return None, (
                f"unresolved runtime: source {instance.source_runtime_id!r} "
                "is disabled or missing"
            )
        return source.base_url, None

    async def _anonymise_kpi(self, session_id: str) -> StoreErasureResult:
        """Anonymise the session's KPI rows (RFC §3.3 default: anonymise, not delete).

        KPI is an analytics aggregate — the identifiers are nulled so counts stay
        intact but the link to a person is severed; `deleted_count` reports the
        number of rows anonymised. The KPI store is optional (no OpenSearch in
        some deployments): an absent store is a no-op ok entry (nothing to
        anonymise), not an error. Like every store the call is isolated — a
        failure records ok=false and never aborts the fan-out. The store call is
        synchronous (OpenSearch client), so it runs off the event loop.
        """
        store = self._deps.get_kpi_store()
        if store is None:
            return StoreErasureResult(store=STORE_KPI, deleted_count=0, ok=True)
        try:
            updated = await asyncio.to_thread(store.anonymise_for_session, session_id)
            return StoreErasureResult(store=STORE_KPI, deleted_count=updated, ok=True)
        except Exception as exc:
            return StoreErasureResult(
                store=STORE_KPI, ok=False, error=f"kpi anonymise failed: {exc}"
            )

    async def _erase_runtime_checkpoint(
        self,
        base_url: str,
        session_id: str,
        authorization: str,
    ) -> StoreErasureResult:
        """DELETE the session's LangGraph checkpoint on its runtime (204)."""
        url = f"{base_url.rstrip('/')}/agents/checkpoints/{session_id}"
        try:
            async with httpx.AsyncClient(timeout=_RUNTIME_TIMEOUT_SECONDS) as client:
                response = await client.delete(
                    url, headers={"Authorization": authorization}
                )
            response.raise_for_status()
            return StoreErasureResult(store=STORE_CHECKPOINT, ok=True)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or str(exc)
            return StoreErasureResult(
                store=STORE_CHECKPOINT,
                ok=False,
                error=f"runtime checkpoint delete failed: {detail}",
            )
        except httpx.RequestError as exc:
            return StoreErasureResult(
                store=STORE_CHECKPOINT,
                ok=False,
                error=f"runtime checkpoint delete request failed: {exc}",
            )

    async def _erase_runtime_history(
        self,
        base_url: str,
        session_id: str,
        authorization: str,
    ) -> StoreErasureResult:
        """DELETE the session transcript on its runtime.

        Reads `{"deleted": n}` into the receipt. The runtime returns
        `{"deleted": 0}` for an already-gone or non-owned session (no error),
        so a second erase is a clean, idempotent no-op.
        """
        url = f"{base_url.rstrip('/')}/agents/sessions/{session_id}"
        try:
            async with httpx.AsyncClient(timeout=_RUNTIME_TIMEOUT_SECONDS) as client:
                response = await client.delete(
                    url, headers={"Authorization": authorization}
                )
            response.raise_for_status()
            deleted = int(response.json().get("deleted", 0))
            return StoreErasureResult(
                store=STORE_HISTORY, deleted_count=deleted, ok=True
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or str(exc)
            return StoreErasureResult(
                store=STORE_HISTORY,
                ok=False,
                error=f"runtime history delete failed: {detail}",
            )
        except httpx.RequestError as exc:
            return StoreErasureResult(
                store=STORE_HISTORY,
                ok=False,
                error=f"runtime history delete request failed: {exc}",
            )
