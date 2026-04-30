from __future__ import annotations

from typing import TYPE_CHECKING, List, Literal, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from agentic_backend.common.structures import AgentChatOptions

KfVectorSearchProviderType = Literal["kf_vector_search"]
KF_VECTOR_SEARCH_PROVIDER: KfVectorSearchProviderType = "kf_vector_search"

SearchPolicyLiteral = Literal["hybrid", "semantic", "strict"]


class KfVectorSearchParams(BaseModel):
    """
    Agent-level scoping parameters for the kf_vector_search inprocess tool.

    Chat options (attach_files, libraries_selection, search_policy_selection) let the
    agent creator opt in to the corresponding UI controls in the chat bar. Setting a
    flag to True surfaces the control; leaving it False leaves the control hidden (the
    default).
    """

    provider: KfVectorSearchProviderType = KF_VECTOR_SEARCH_PROVIDER
    document_library_tags_ids: List[str] = Field(
        default=[],
        description=(
            "Hard library binding set at agent creation time. "
            "When non-empty, the agent searches ONLY these libraries regardless of any "
            "runtime user selection — the library picker is hidden in the chat bar. "
            "Empty (default) means no restriction: the user can pick libraries at runtime."
        ),
    )
    attach_files: bool = Field(
        default=False,
        description=(
            "When True, expose the file-attachment control in the chat bar so users "
            "can attach local files (PDFs, images, text) to their messages."
        ),
    )
    libraries_selection: bool = Field(
        default=False,
        description=(
            "When True, expose the document-library picker in the chat bar so users "
            "can narrow retrieval to specific libraries at message time."
        ),
    )
    search_policy: Optional[SearchPolicyLiteral] = Field(
        default="semantic",
        description=(
            "Default retrieval strategy for this agent. hybrid combines BM25 and vector "
            "search (RRF); semantic uses vector search only; strict applies a high-precision "
            "similarity threshold. Overridden at runtime by the user's chat-bar selection "
            "when search_policy_selection is True."
        ),
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description=(
            "Maximum number of document chunks returned per search call. When set, overrides "
            "the model's dynamic choice. Leave unset to let the model decide (default: 10). "
            "Increase for large heterogeneous corpora where relevant documents are sparse."
        ),
    )
    search_policy_selection: bool = Field(
        default=False,
        description=(
            "When True, expose the search-policy selector in the chat bar so users "
            "can switch retrieval strategy per message."
        ),
    )

    def edit_chat_options(self, options: AgentChatOptions) -> None:
        """
        Contribute chat-bar UI flags implied by these tool params.

        Mutates `options` in-place. The caller is responsible for passing a copy.
        Only sets flags to True — existing True values are never overridden to False.
        """
        if self.attach_files:
            options.attach_files = True
        if self.document_library_tags_ids:
            # Hard binding is active: library picker must be hidden in chat.
            options.libraries_selection = False
        elif self.libraries_selection:
            options.libraries_selection = True
        if self.search_policy_selection:
            options.search_policy_selection = True
