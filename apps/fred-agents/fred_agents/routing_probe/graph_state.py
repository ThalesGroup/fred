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

"""
Input and state models for the routing probe agent (#2267).

Every turn runs the same three model calls (`routing`, `planning`,
`execution`), each carrying its own `operation` label to `invoke_model`, so
one message exercises every phase a team-routing-policy override could
target.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoutingProbeInput(BaseModel):
    """User message — content is echoed back into each phase call, not parsed."""

    message: str = Field(..., min_length=1)


class PhaseRecord(BaseModel):
    """One resolved model call, recorded for the final summary table."""

    phase: str
    operation: str
    model_name: str
    reply: str
    # CACHE-01: input/cache_read tokens for this one phase's call — None when
    # no model was configured or the provider didn't report cache detail.
    input_tokens: int | None = None
    cache_read_tokens: int | None = None


class RoutingProbeState(BaseModel):
    """Minimal workflow state — one record per phase, plus the assembled reply."""

    latest_user_text: str

    phase_records: list[PhaseRecord] = Field(default_factory=list)

    final_text: str | None = None
    done_reason: str | None = None

    # Set by runtime on node errors
    node_error: str = ""
