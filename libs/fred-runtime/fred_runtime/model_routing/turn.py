# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Non-serializable, single-use authority owned by the existing RunScope."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DocumentAccessContext
from fred_sdk.contracts.context import PortableContext, RuntimeContext
from fred_sdk.contracts.weaver import (
    ModelOfferKey,
    RuntimeModelOffer,
    WeaverRuntimeBinding,
)

from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.request_context_helpers import (
    get_document_library_tags_ids,
    get_document_uids,
    get_rag_knowledge_scope,
    get_vector_search_scopes,
)
from fred_runtime.runtime_support.run_scope import RunScope

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class TurnAuthority:
    def __init__(
        self,
        binding: WeaverRuntimeBinding,
        choice: ModelOfferKey | None,
        *,
        reasoning: bool = False,
    ):
        self.binding = binding
        self.choice = choice
        self._reasoning_requested = reasoning
        self._scope: RunScope | None = None
        self._ended = False
        self.models: dict[ModelOfferKey, BaseChatModel] = {}
        self._documents: DocumentAccessContext | None = None

    def bind_documents(
        self,
        context: RuntimeContext,
        scope: DocumentScope,
        *,
        attachments_enabled: bool,
    ) -> None:
        """Fix source choices once; retries and descendants inherit this ceiling."""
        self.check_context(context, self.binding.agent.template_key)
        if self._documents is None:
            base = self.document_context(context, scope)
            session, _ = get_vector_search_scopes(context)
            attachments = (
                tuple(item.document_id for item in self.binding.attachments)
                if attachments_enabled
                and session
                and get_rag_knowledge_scope(context) != "general_only"
                else ()
            )
            self._documents = DocumentAccessContext(
                space_id=base.space_id,
                document_scope=base.document_scope,
                conversation_id=UUID(self.binding.conversation_id)
                if attachments
                else None,
                attachment_ids=attachments,
            )

    def document_context(
        self,
        context: RuntimeContext,
        bound: DocumentScope = DocumentScope(),
        *,
        include_attachments: bool = True,
        include_corpus: bool = True,
    ) -> DocumentAccessContext:
        """One source filter for HTTP, MCP and prompts; callers can only narrow it."""
        self.check_context(context, self.binding.agent.template_key)
        scope = bound.intersect(
            DocumentScope.from_ids(
                get_document_library_tags_ids(context), get_document_uids(context)
            )
        )
        attachments = ()
        conversation = None
        if self._documents is not None:
            scope = self._documents.document_scope.intersect(scope)
            attachments = self._documents.attachment_ids
            conversation = self._documents.conversation_id
        session, corpus = get_vector_search_scopes(context)
        general_only = get_rag_knowledge_scope(context) == "general_only"
        if general_only or not (corpus and include_corpus):
            scope = scope.intersect(DocumentScope.from_ids([], []))
        if general_only or not (session and include_attachments):
            attachments = ()
        return DocumentAccessContext(
            space_id=self.binding.space.id,
            document_scope=scope,
            conversation_id=conversation,
            attachment_ids=attachments,
        )

    def reasoning_effort(self, offer: RuntimeModelOffer) -> str | None:
        if (
            self._reasoning_requested
            and offer.permitted
            and offer.candidate
            and offer.key in self.binding.models.policy.reasoning_enabled
            and offer.metadata is not None
            and offer.metadata.reasoning is True
        ):
            # Preserve Swift's on/off mode: its connected chat profiles use high.
            return "high"
        return None

    def start(self, scope: RunScope) -> None:
        if self._scope is not None or self._ended:
            raise AuthorityLostError()
        self._scope = scope

    def close(self) -> None:
        self._ended = True
        self.models.clear()

    def check(self, *, agent_id: str | None = None) -> None:
        scope = self._scope
        if (
            self._ended
            or scope is None
            or scope.closed
            or RunScope.current() is not scope
        ):
            raise AuthorityLostError()
        scope.raise_if_stopped()
        # M3 admits one template. It confers no authority over another template.
        if agent_id is not None and agent_id != self.binding.agent.template_key:
            raise AuthorityLostError()

    def check_context(
        self, context: RuntimeContext | PortableContext, agent_id: str
    ) -> None:
        self.check(agent_id=agent_id)
        b = self.binding
        if isinstance(context, PortableContext):
            space_id = context.baggage.get("space_id")
            instance_id = context.baggage.get("agent_instance_id")
        else:
            space_id = context.space_id
            instance_id = context.agent_instance_id
        if (
            context.user_id != b.subject_id
            or context.session_id != b.conversation_id
            or space_id != str(b.space.id)
            or instance_id != str(b.agent.instance_id)
        ):
            raise AuthorityLostError()


def current_turn() -> TurnAuthority:
    scope = RunScope.current()
    authority = scope.turn_authority if scope is not None else None
    if authority is None:
        raise AuthorityLostError()
    authority.check()
    return authority
