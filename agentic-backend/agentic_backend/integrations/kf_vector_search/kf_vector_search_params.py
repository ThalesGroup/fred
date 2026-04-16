from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

KfVectorSearchProviderType = Literal["kf_vector_search"]
KF_VECTOR_SEARCH_PROVIDER: KfVectorSearchProviderType = "kf_vector_search"


class KfVectorSearchParams(BaseModel):
    """
    Agent-level scoping parameters for the kf_vector_search inprocess tool.

    Set at agent creation time; act as the broadest allowed scope.
    User runtime selection and LLM tool-call selection are clamped within this set.
    """

    provider: KfVectorSearchProviderType = KF_VECTOR_SEARCH_PROVIDER
    document_library_tags_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "Restrict semantic search to these document library tag IDs. "
            "User and LLM selections are intersected with this set at query time."
        ),
    )
