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
Contracts for the POST /agents/evaluate endpoint.

EvalTrace is the synchronous JSON response that evaluation harnesses
(DeepEval, Promptfoo, custom) consume — no SSE parsing, no Langfuse dependency.
"""

from fred_sdk.contracts.models import FrozenModel


class EvalStep(FrozenModel):
    """One step in the agent execution trace."""

    kind: str  # tool_call | tool_result | final | node_error | awaiting_human
    tool_name: str | None = None
    call_id: str | None = None
    arguments: dict[str, object] | None = None
    content: str | None = None
    is_error: bool | None = None
    node_id: str | None = None
    error_message: str | None = None


class EvalTrace(FrozenModel):
    """
    Full evaluation trace for one agent turn.

    Designed to satisfy DeepEval / Promptfoo evaluation harnesses directly:
    - input / output / retrieval_context map to LLMTestCase fields
    - steps provides the ordered execution trace for tool-correctness metrics
    - tools_called is a convenience list of tool names in invocation order
    """

    session_id: str
    agent_id: str
    agent_tags: tuple[str, ...] = ()
    input: str
    output: str | None = None
    error: str | None = None
    latency_ms: int
    model_name: str | None = None
    token_usage: dict[str, int] | None = None  # keys: input_tokens, output_tokens
    finish_reason: str | None = None
    steps: tuple[EvalStep, ...] = ()
    retrieval_context: tuple[str, ...] = ()  # non-error tool_result contents, in order
    tools_called: tuple[str, ...] = ()  # tool names in call order
