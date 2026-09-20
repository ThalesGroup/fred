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

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .capability import (
        AgentCapability,
        AssetSlot,
        CapabilityContext,
        CapabilityIdentity,
        CapabilityManifest,
        ChatControlSpec,
        EmptyModel,
        HitlGateRequest,
        HitlSpec,
        SaveContext,
        SidePanelSpec,
        TeamScopePolicy,
        UploadedFile,
        chat_part_kind,
    )
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
        ExecutionGrantAction,
        ExecutionTarget,
        RuntimeExecuteRequest,
        TeamContext,
        TeamType,
        TraceContext,
    )
    from .openai_compat import (
        OpenAIModelCard,
        OpenAIModelList,
        OpenAIToolCall,
        OpenAIToolCallFunction,
    )
    from .prompt_utils import (
        PROMPT_SAFE_TOKENS,
        RESERVED_PROMPT_TAGS,
        escape_reserved_prompt_tags,
        find_reserved_prompt_tag,
    )
    from .runtime import RuntimeErrorEvent, TurnPersistedEvent
    from .ui_part_union import (
        BASE_UI_PARTS,
        current_ui_part_union,
        rebuild_ui_part_union,
    )

# Exported name -> module that defines it. Eager imports here dragged langchain
# (.capability) and the whole fred_core tree (.context, .runtime) into every
# consumer, including lean pods that only wanted a single contract type.
_LAZY: dict[str, str] = {
    # Capability contracts
    "AgentCapability": "fred_sdk.contracts.capability",
    "AssetSlot": "fred_sdk.contracts.capability",
    "CapabilityContext": "fred_sdk.contracts.capability",
    "CapabilityIdentity": "fred_sdk.contracts.capability",
    "CapabilityManifest": "fred_sdk.contracts.capability",
    "ChatControlSpec": "fred_sdk.contracts.capability",
    "EmptyModel": "fred_sdk.contracts.capability",
    "HitlGateRequest": "fred_sdk.contracts.capability",
    "HitlSpec": "fred_sdk.contracts.capability",
    "SaveContext": "fred_sdk.contracts.capability",
    "SidePanelSpec": "fred_sdk.contracts.capability",
    "TeamScopePolicy": "fred_sdk.contracts.capability",
    "UploadedFile": "fred_sdk.contracts.capability",
    "chat_part_kind": "fred_sdk.contracts.capability",
    # Conversational memory / context / UI parts
    "ConversationalState": "fred_sdk.contracts.context",
    "ConversationTurn": "fred_sdk.contracts.context",
    "GeoPart": "fred_sdk.contracts.context",
    "LinkKind": "fred_sdk.contracts.context",
    "LinkPart": "fred_sdk.contracts.context",
    "RuntimeContext": "fred_sdk.contracts.context",
    # Execution identity and authorization
    "ActorContext": "fred_sdk.contracts.execution",
    "ExecutionGrantAction": "fred_sdk.contracts.execution",
    "ExecutionTarget": "fred_sdk.contracts.execution",
    "RuntimeExecuteRequest": "fred_sdk.contracts.execution",
    "TeamContext": "fred_sdk.contracts.execution",
    "TeamType": "fred_sdk.contracts.execution",
    "TraceContext": "fred_sdk.contracts.execution",
    # OpenAI compat
    "OpenAIModelCard": "fred_sdk.contracts.openai_compat",
    "OpenAIModelList": "fred_sdk.contracts.openai_compat",
    "OpenAIToolCall": "fred_sdk.contracts.openai_compat",
    "OpenAIToolCallFunction": "fred_sdk.contracts.openai_compat",
    # Prompt token registry and reserved tags
    "PROMPT_SAFE_TOKENS": "fred_sdk.contracts.prompt_utils",
    "RESERVED_PROMPT_TAGS": "fred_sdk.contracts.prompt_utils",
    "escape_reserved_prompt_tags": "fred_sdk.contracts.prompt_utils",
    "find_reserved_prompt_tag": "fred_sdk.contracts.prompt_utils",
    # Runtime events
    "RuntimeErrorEvent": "fred_sdk.contracts.runtime",
    "TurnPersistedEvent": "fred_sdk.contracts.runtime",
    # UiPart union registration
    "BASE_UI_PARTS": "fred_sdk.contracts.ui_part_union",
    "current_ui_part_union": "fred_sdk.contracts.ui_part_union",
    "rebuild_ui_part_union": "fred_sdk.contracts.ui_part_union",
}


def __getattr__(name: str) -> object:
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value  # resolved once, then a normal global
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    # Capability contracts (#1973, RFC AGENT-CAPABILITY-RFC.md §3)
    "AgentCapability",
    "AssetSlot",
    "CapabilityContext",
    "CapabilityIdentity",
    "CapabilityManifest",
    "ChatControlSpec",
    "EmptyModel",
    "HitlGateRequest",
    "HitlSpec",
    "SaveContext",
    "SidePanelSpec",
    "TeamScopePolicy",
    "UploadedFile",
    "chat_part_kind",
    # Conversational memory
    "ConversationTurn",
    "ConversationalState",
    # Context / UI parts
    "GeoPart",
    "LinkKind",
    "LinkPart",
    "RuntimeContext",
    # UiPart union registration (#1977, RFC AGENT-CAPABILITY-RFC.md §3.6/§4)
    "BASE_UI_PARTS",
    "current_ui_part_union",
    "rebuild_ui_part_union",
    # Execution identity and authorization (Phase 1)
    "ActorContext",
    "TeamContext",
    "TeamType",
    "ExecutionTarget",
    "TraceContext",
    "ExecutionGrantAction",
    "RuntimeExecuteRequest",
    # Runtime events (Phase 1 addition)
    "TurnPersistedEvent",
    "RuntimeErrorEvent",
    # OpenAI compat — typed tool call models
    "OpenAIModelCard",
    "OpenAIModelList",
    "OpenAIToolCall",
    "OpenAIToolCallFunction",
    # Prompt template token registry and reserved system-prompt tags
    "PROMPT_SAFE_TOKENS",
    "RESERVED_PROMPT_TAGS",
    "escape_reserved_prompt_tags",
    "find_reserved_prompt_tag",
]
