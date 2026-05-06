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
Reviewed v2 contract surface.

Why this package exists:
- group the pure/shared contract files that define the reviewed v2 boundary
- make the separation visible between author/runtime contracts and implementation files

How to use:
- import from these modules when you need the stable v2 contract types directly
- keep SDK-specific runtime code outside this package
"""

from .context import (
    ConversationalState,
    ConversationTurn,
    GeoPart,
    LinkKind,
    LinkPart,
    RuntimeContext,
)
from .execution import (
    ActorContext,
    ExecutionGrant,
    ExecutionGrantAction,
    ExecutionGrantViolation,
    ExecutionTarget,
    RuntimeExecuteRequest,
    TeamContext,
    TeamType,
    TraceContext,
    validate_execution_grant,
)
from .openai_compat import (
    OpenAIModelCard,
    OpenAIModelList,
    OpenAIToolCall,
    OpenAIToolCallFunction,
)
from .runtime import RuntimeErrorEvent, TurnPersistedEvent

__all__ = [
    # Conversational memory
    "ConversationTurn",
    "ConversationalState",
    # Context / UI parts
    "GeoPart",
    "LinkKind",
    "LinkPart",
    "RuntimeContext",
    # Execution identity and authorization (Phase 1)
    "ActorContext",
    "TeamContext",
    "TeamType",
    "ExecutionTarget",
    "TraceContext",
    "ExecutionGrant",
    "ExecutionGrantAction",
    "ExecutionGrantViolation",
    "RuntimeExecuteRequest",
    "validate_execution_grant",
    # Runtime events (Phase 1 addition)
    "TurnPersistedEvent",
    "RuntimeErrorEvent",
    # OpenAI compat — typed tool call models
    "OpenAIModelCard",
    "OpenAIModelList",
    "OpenAIToolCall",
    "OpenAIToolCallFunction",
]
