# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Union

from attr import dataclass
from langchain_core.documents import Document
from pydantic import BaseModel

CHUNK_ID_FIELD = "chunk_uid"  # your canonical per-chunk id in metadata


def is_own_session_chunk(chunk: Dict[str, Any], user_id: str) -> bool:
    """True if a vector chunk is a session-scoped attachment chunk owned by `user_id`.

    Session attachments (fast-ingest) carry no ReBAC tuple and no metadata-store
    record — this chunk-level marker (`scope`, `user_id`) is the only ownership
    signal that exists for them, so every authorization decision over that scope
    (read reconstruction, delete) must go through this same check rather than a
    document-level ReBAC lookup, which can never resolve for an untagged document.
    """
    metadata = chunk.get("metadata") or {}
    return metadata.get("scope") == "session" and metadata.get("user_id") == user_id


@dataclass(frozen=True)
class SearchFilter:
    """
    Backend-agnostic filter.
    - document_ids: hard scope by doc_uid (library scoping resolved upstream)
    - metadata_terms: exact keyword filters on metadata fields
    """

    tag_ids: Optional[Sequence[str]] = None
    # Accept JSON-like scalar values for metadata filtering (str, int, float, bool)
    # Use Mapping for covariance to allow callers to pass dict[str, list[bool]] safely.
    metadata_terms: Optional[Mapping[str, Sequence[Union[str, int, float, bool]]]] = None


class BaseVectorHit(BaseModel):
    document: Document
    score: float


class AnnHit(BaseVectorHit):
    pass


class HybridHit(BaseVectorHit):
    pass


class FullTextHit(BaseVectorHit):
    pass


class BaseVectorStore(ABC):
    """
    Minimal, backend-agnostic interface every store implements.
    - Ingestion (idempotent via stable ids)
    - ANN search (semantic)
    """

    @abstractmethod
    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        """Upsert chunks; return assigned ids (prefer stable chunk_uids)."""
        raise NotImplementedError

    @abstractmethod
    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        """Delete all chunks for a logical document."""
        raise NotImplementedError

    def set_document_retrievable(self, *, document_uid: str, value: bool) -> None:  # pragma: no cover - optional capability
        """
        Optional capability: update the 'retrievable' flag for all chunks of a document
        without deleting vectors. Concrete stores that support this should override.
        """
        raise NotImplementedError("This vector store does not support retrievable toggling.")

    def set_document_name(self, *, document_uid: str, document_name: str) -> None:  # pragma: no cover - optional capability
        """
        Optional capability: update the 'document_name' metadata field for all chunks
        of a document without deleting vectors or re-embedding. Concrete stores that
        support this should override. Called (best-effort) after a document rename.
        """
        raise NotImplementedError("This vector store does not support renaming.")

    def get_vectors_for_document(self, document_uid: str, with_document: bool = True) -> List[Dict[str, Any]]:
        """Optional capability: fetch raw vector data for all chunks of a document."""
        raise NotImplementedError("This vector store does not support fetching raw vectors.")

    def get_chunks_for_document(self, document_uid: str) -> List[Dict[str, Any]]:
        """Optional capability: fetch raw chunk data for all chunks of a document."""
        raise NotImplementedError("This vector store does not support fetching raw chunks.")

    def may_delete_session_document(self, document_uid: str, user_id: str) -> bool:
        """True if `user_id` may delete `document_uid` as a session-scoped attachment.

        True when the user owns at least one chunk of the document, OR the
        document has no chunks at all. The empty case matters for retry
        safety: deleting a session document's vectors is itself idempotent
        (deleting nothing is a no-op), so if an earlier delete attempt already
        removed every chunk before failing on a later cleanup step, a retry
        must still be allowed to reach that step rather than being denied
        forever because there is nothing left to prove ownership over.

        Fails closed (returns False) when chunks exist but none belong to
        `user_id`, or when the backend can't fetch chunks by document at all
        (an unsupported backend can't distinguish "nothing to delete" from
        "someone else's document").
        """
        try:
            chunks = self.get_chunks_for_document(document_uid)
        except NotImplementedError:
            return False
        if not chunks:
            return True
        return any(is_own_session_chunk(c, user_id) for c in chunks)

    def get_chunk(self, document_uid: str, chunk_uid: str) -> Dict[str, Any]:
        """Optional capability: fetch raw chunk data for all chunks of a document."""
        raise NotImplementedError("This vector store does not support fetching raw chunks.")

    def delete_chunk(self, document_uid: str, chunk_uid: str) -> None:
        """Optional capability: delete chunks for a logical document."""
        raise NotImplementedError("This vector store does not support deleting raw chunks.")

    @abstractmethod
    def ann_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None) -> List[AnnHit]:
        """Semantic (ANN) search; should honor SearchFilter where supported."""
        raise NotImplementedError

    def list_document_uids(self) -> list[str]:  # pragma: no cover - optional capability
        """
        Optional helper: return distinct document_uids tracked by the vector store.
        """
        return []


class FetchById(Protocol):
    """
    Capability: hydrate Documents from chunk ids.
    Useful if your lexical returns only ids.
    """

    def fetch_documents(self, chunk_ids: Sequence[str]) -> List[Document]: ...
