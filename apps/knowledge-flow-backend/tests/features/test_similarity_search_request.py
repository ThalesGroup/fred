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

"""The unified search request keeps ordinary defaults and optional similarity controls."""

import pytest
from pydantic import ValidationError

from knowledge_flow_backend.features.vector_search.vector_search_structures import SearchRequest


def test_search_defaults_preserve_ordinary_retrieval() -> None:
    req = SearchRequest(question="some passage")
    assert req.rerank is False
    assert req.min_score is None
    assert req.top_k == 10
    assert req.search_policy is None


def test_similarity_controls_are_optional_and_documented() -> None:
    req = SearchRequest(question="anchor", rerank=True, min_score=0.2)
    assert req.rerank is True
    assert req.min_score == 0.2
    schema = SearchRequest.model_json_schema()
    for field in ("rerank", "min_score"):
        assert field not in schema["required"]
        assert schema["properties"][field]["description"]


@pytest.mark.parametrize("top_k", [0, 101, 200])
def test_top_k_is_bounded(top_k: int) -> None:
    with pytest.raises(ValidationError):
        SearchRequest(question="x", top_k=top_k)


@pytest.mark.parametrize("field", ["document_uids", "document_library_tags_ids", "attachment_ids"])
def test_targets_cannot_be_supplied_in_the_search_body(field: str) -> None:
    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"question": "x", field: ["doc-1"]})
