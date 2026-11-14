# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The working space's organization models, as the Control Plane publishes them.

Search embeds a question with the organization's locked corpus model; document tools
use its default chat model. Both come from the Control Plane's `cp_read` facts in the
request's snapshot, never from this workload's configuration.
"""

from __future__ import annotations

from typing import Literal, NamedTuple
from uuid import UUID

from fastapi import HTTPException
from fred_core.documents.transport import DocumentAccessContext
from fred_knowledge.models import DocumentModelError
from fred_sdk.contracts.weaver import EffectiveModelOptions, InferenceAdmission, InferenceSelection, ModelConnection, ModelOfferKey
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

ModelUse = Literal["embedding", "chat", "rerank"]

_MODEL = text(
    "SELECT organization_id, source_id, upstream_model_id, connection, source_revision,"
    " snapshot_revision, policy_revision, available"
    " FROM cp_read.organization_model WHERE space_id = :space_id AND use = :use"
)


class OrganizationModelUnavailable(RuntimeError):
    """The organization chose a model whose source or offer is not usable now."""


class OrganizationModel(NamedTuple):
    organization_id: UUID
    admission: InferenceAdmission


async def organization_model(conn: AsyncConnection, space_id: UUID, use: ModelUse) -> OrganizationModel | None:
    """None when the organization has no such model: no indexed corpus, or no default."""
    row = (await conn.execute(_MODEL, {"space_id": space_id, "use": use})).mappings().first()
    if row is None:
        return None
    if not row["available"]:
        raise OrganizationModelUnavailable(f"The organization's {use} model is unavailable")
    selection = InferenceSelection(
        key=ModelOfferKey(source_id=row["source_id"], upstream_model_id=row["upstream_model_id"]),
        source="default",
        options=EffectiveModelOptions(),
        source_revision=row["source_revision"],
        snapshot_revision=row["snapshot_revision"],
        policy_revision=row["policy_revision"],
    )
    admission = InferenceAdmission(selection=selection, connection=ModelConnection.model_validate(row["connection"]))
    return OrganizationModel(row["organization_id"], admission)


async def organization_chat_model(context: DocumentAccessContext) -> tuple[BaseChatModel, str]:
    """The space organization's default chat model, for document tools; HTTP errors otherwise."""
    from knowledge_flow_backend.application_context import ApplicationContext

    application = ApplicationContext.get_instance()
    async with application.get_pg_async_engine().connect() as conn:
        try:
            model = await organization_model(conn, context.space_id, "chat")
        except OrganizationModelUnavailable:
            raise HTTPException(status_code=503, detail="organization_default_model_unavailable") from None
    if model is None:
        raise HTTPException(status_code=409, detail="organization_default_model_required")
    try:
        chat = application.get_document_models().chat(model.admission)
    except DocumentModelError:
        raise HTTPException(status_code=503, detail="organization_default_model_unavailable") from None
    return chat, model.admission.selection.key.upstream_model_id
