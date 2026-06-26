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

"""Input and state for the deterministic self-test RAG agent."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SelfTestInput(BaseModel):
    """The question to retrieve an answer for."""

    message: str = Field(..., min_length=1)


class SelfTestState(BaseModel):
    """Minimal state: the question in, the echoed retrieval out."""

    latest_user_text: str

    # Written by the retrieve step, read by build_output.
    sources_data: list[dict[str, object]] = Field(default_factory=list)
    hit_count: int = 0

    final_text: str | None = None
    done_reason: str | None = None
