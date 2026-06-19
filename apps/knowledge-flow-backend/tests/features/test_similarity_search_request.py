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

"""Unit tests for the SimilaritySearchRequest contract (KF-SIMILARITY-SEARCH).

Covers the stable request interface: targeting is required, the anchor is
required, and the search defaults (rerank on, top_k bounds). The service
orchestration depends on the vector store + ApplicationContext and is
integration-level, not unit-tested here.
"""

import pytest
from pydantic import ValidationError

from knowledge_flow_backend.features.vector_search.vector_search_structures import (
    SimilaritySearchRequest,
)


def test_accepts_document_uid_target() -> None:
    req = SimilaritySearchRequest(anchor="some passage", document_uids=["doc-1"])
    assert req.document_uids == ["doc-1"]
    # defaults: rerank on, top_k 10
    assert req.rerank is True
    assert req.top_k == 10


def test_accepts_library_folder_target() -> None:
    req = SimilaritySearchRequest(anchor="x", document_library_tags_ids=["lib-1"])
    assert req.document_library_tags_ids == ["lib-1"]


def test_targeting_is_required() -> None:
    with pytest.raises(ValidationError):
        SimilaritySearchRequest(anchor="x")  # no document_uids and no tags


def test_anchor_is_required() -> None:
    with pytest.raises(ValidationError):
        SimilaritySearchRequest(anchor="", document_uids=["doc-1"])


def test_top_k_is_bounded() -> None:
    with pytest.raises(ValidationError):
        SimilaritySearchRequest(anchor="x", document_uids=["doc-1"], top_k=200)
