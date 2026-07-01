"""Conversation erasure — single fan-out entry point (CTRLP-12, RFC §3.A).

`ConversationErasureService.erase_session` erases one conversation across every
store the control-plane owns and returns an auditable `ErasureReceipt`
(per store: count, ok, error).

A1 scope is a **pure refactor**: it lifts the existing `delete_session` body —
attachments (+ Knowledge Flow artifacts) and session metadata — behind this
service, unchanged, and wraps it in a receipt. No new stores are erased here;
the runtime history + checkpoint erasers (A2) and the KPI eraser (A3) append
their own receipt entries later, reusing this fan-out shape.
"""

from __future__ import annotations

from fred_core.common import TeamId
from pydantic import BaseModel, Field, computed_field

from control_plane_backend.product import service as product_service
from control_plane_backend.product.dependencies import ProductServiceDependencies

# Stable store identifiers used as receipt keys (A2/A3 add more).
STORE_ATTACHMENTS = "attachments"
STORE_SESSION_METADATA = "session_metadata"


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

        Behaviour is identical to the former `delete_session`: it validates
        team + ownership, cleans each attachment's Knowledge Flow artifacts,
        removes the attachment rows, then deletes the session metadata row.
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

        return receipt
