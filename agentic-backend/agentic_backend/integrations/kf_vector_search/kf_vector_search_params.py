from __future__ import annotations

from typing import TYPE_CHECKING, List, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from agentic_backend.common.structures import AgentChatOptions

KfVectorSearchProviderType = Literal["kf_vector_search"]
KF_VECTOR_SEARCH_PROVIDER: KfVectorSearchProviderType = "kf_vector_search"


class KfVectorSearchParams(BaseModel):
    """
    Agent-level scoping parameters for the kf_vector_search inprocess tool.

    Set at agent creation time; act as the broadest allowed scope.
    User runtime selection and LLM tool-call selection are clamped within this set.

    Chat options (attach_files, libraries_selection) let the agent creator opt in to
    the corresponding UI controls in the chat bar.  Setting a flag to True surfaces the
    control; leaving it False leaves the control hidden (the default).
    """

    provider: KfVectorSearchProviderType = KF_VECTOR_SEARCH_PROVIDER
    document_library_tags_ids: List[str] = Field(
        default=[],
        description=(
            "Restrict semantic search to these document library tag IDs. "
            "User and LLM selections are intersected with this set at query time."
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

    def edit_chat_options(self, options: AgentChatOptions) -> None:
        """
        Contribute chat-bar UI flags implied by these tool params.

        Mutates `options` in-place. The caller is responsible for passing a copy.
        Only sets flags to True — existing True values are never overridden to False.
        """
        if self.attach_files:
            options.attach_files = True
        if self.libraries_selection:
            options.libraries_selection = True
