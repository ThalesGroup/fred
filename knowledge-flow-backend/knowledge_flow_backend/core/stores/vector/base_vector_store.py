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
from typing import Dict, List, Optional, Protocol, Sequence, runtime_checkable

from attr import dataclass
from langchain_core.documents import Document

CHUNK_ID_FIELD = "chunk_uid"  # your canonical per-chunk id in metadata


@dataclass(frozen=True)
class SearchFilter:
    """
    Backend-agnostic filter.
    - document_ids: hard scope by doc_uid (library scoping resolved upstream)
    - metadata_terms: exact keyword filters on metadata fields
    """

    tag_ids: Optional[Sequence[str]] = None
    metadata_terms: Optional[Dict[str, Sequence[str]]] = None


@dataclass(frozen=True)
class AnnHit:
    """Semantic hit with hydrated Document (used directly for UI)."""

    document: Document
    score: float  # cosine in [0,1] if normalized


@dataclass(frozen=True)
class LexicalHit:
    """Lexical hit returns ids + score; hydrate on demand if needed."""

    chunk_id: str
    score: float


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

    @abstractmethod
    def ann_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None) -> List[AnnHit]:
        """Semantic (ANN) search; should honor SearchFilter where supported."""
        raise NotImplementedError


@runtime_checkable
class LexicalSearchable(Protocol):
    """
    Capability: BM25 + phrase search.
    A store that implements this can be used by 'hybrid' and 'strict'.
    """

    def lexical_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None, operator_and: bool = True) -> List[LexicalHit]: ...
    def phrase_search(self, phrase: str, *, fields: Sequence[str], k: int, search_filter: Optional[SearchFilter] = None) -> List[str]: ...


class FetchById(Protocol):
    """
    Capability: hydrate Documents from chunk ids.
    Useful if your lexical returns only ids.
    """

    def fetch_documents(self, chunk_ids: Sequence[str]) -> List[Document]: ...
