# Copyright Thales 2026
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

"""Wiki search wire models retain bounded results and server continuation."""

from __future__ import annotations

import pytest
from fred_sdk.contracts.runtime import WikiSearchResult
from pydantic import ValidationError


@pytest.mark.parametrize(
    "next_offset, truncated", [(None, False), (37, False), (None, True)]
)
def test_search_wire_contract_keeps_candidate_continuation(
    next_offset: int | None, truncated: bool
) -> None:
    payload = {
        "hits": [
            {
                "page_id": "c2521b17-d188-429d-af7a-50b714b5266e",
                "slug": "support",
                "title": "Support",
                "page_type": "procedure",
                "description": None,
                "excerpt": "é" * 300,
            }
        ],
        "next_offset": next_offset,
        "truncated": truncated,
    }
    result = WikiSearchResult.model_validate(payload)
    assert result.model_dump(mode="json") == payload
    assert isinstance(result.hits, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        result.hits[0].excerpt = "replacement"
    with pytest.raises(ValidationError, match="frozen"):
        result.next_offset = 1


def test_empty_search_batch_can_still_continue() -> None:
    result = WikiSearchResult.model_validate(
        {"hits": [], "next_offset": 12, "truncated": True}
    )
    assert result.hits == ()
    assert result.next_offset == 12
    assert result.truncated
