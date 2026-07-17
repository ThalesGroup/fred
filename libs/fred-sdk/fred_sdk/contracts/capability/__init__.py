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
Tier 0 capability contracts (#1973, RFC docs/swift/rfc/AGENT-CAPABILITY-RFC.md §3).

Why this package exists:
- one abstraction (`AgentCapability`) carries a modular agent feature end to
  end: declaration (`CapabilityManifest`), save-time validation, computed chat
  surface, HITL declarations, and the runtime middleware stack
- the runtime half (registry, boot validation, entry-point discovery, agent
  assembly) lives in `fred_runtime.capabilities` — this package is the pure
  contract surface capability authors import

How to use:
- `from fred_sdk.contracts.capability import AgentCapability, CapabilityManifest, ...`
- one module per concern: `base` (the ABC), `manifest` (declaration),
  `context` (typed runtime/LLM split), `hitl` (approval declarations)
"""

from __future__ import annotations

from ..models import StoredCapabilityConfig
from .base import AgentCapability
from .chat_controls import (
    ChatControlsRequest,
    ChatControlsRequestItem,
    ChatControlsResponse,
    ChatControlsResult,
)
from .context import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    SaveContext,
)
from .hitl import HitlGateRequest, HitlSpec
from .manifest import (
    AssetSlot,
    CapabilityCatalogEntry,
    CapabilityManifest,
    ChatControlDescriptor,
    ChatControlItem,
    ChatControlSpec,
    SidePanelSpec,
    TeamScopePolicy,
    UploadedFile,
    chat_part_kind,
)

__all__ = [
    "AgentCapability",
    "AssetSlot",
    "CapabilityCatalogEntry",
    "CapabilityContext",
    "CapabilityIdentity",
    "CapabilityManifest",
    "ChatControlDescriptor",
    "ChatControlItem",
    "ChatControlSpec",
    "ChatControlsRequest",
    "ChatControlsRequestItem",
    "ChatControlsResponse",
    "ChatControlsResult",
    "EmptyModel",
    "HitlGateRequest",
    "HitlSpec",
    "SaveContext",
    "SidePanelSpec",
    "StoredCapabilityConfig",
    "TeamScopePolicy",
    "UploadedFile",
    "chat_part_kind",
]
