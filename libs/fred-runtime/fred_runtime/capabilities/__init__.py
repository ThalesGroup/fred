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
Capability runtime: registry, boot validation, discovery, agent assembly
(#1973, RFC docs/swift/rfc/AGENT-CAPABILITY-RFC.md §4, §5.3).

Why this package exists:
- the contract half of the capability system lives in
  `fred_sdk.contracts.capability`; this package is the runtime half — the ONE
  registry (boot validation + `fred.capabilities` entry-point discovery) and
  the assembly that turns selected capabilities into the middleware block the
  platform frame reserves (`fred_runtime.react.middleware.frame`)

Modules (one per concern):
- `errors`   — named boot/assembly errors (fail pod startup loudly)
- `registry` — `CapabilityRegistry`, `boot_capability_registry`
- `assembly` — typed context resolution + the id-sorted capability block
- `demo`     — the minimal in-tree tracer capability (one tool, one setting)
"""

from __future__ import annotations

from .assembly import (
    CapabilityAgentBlock,
    build_capability_agent_block,
    build_capability_context,
    build_capability_contexts,
    evaluate_capability_chat_controls,
    evaluate_chat_controls_batch,
    resolve_stored_config,
    validate_turn_options,
)
from .assets import enforce_asset_slots
from .errors import (
    AssetSlotViolationError,
    CapabilityAssemblyError,
    CapabilityConfigInvalidError,
    CapabilityError,
    CapabilityRegistrationError,
    CapabilityTableHygieneError,
    DefaultOnRequiredSettingsError,
    DuplicateCapabilityIdError,
    DuplicateChatPartKindError,
    MissingRequiredEnvError,
    TurnOptionsInvalidError,
    UnknownCapabilityError,
)
from .mcp import (
    MCP_CAPABILITY_SCHEMA_VERSION,
    McpCapability,
    McpServerConfig,
    build_mcp_capability,
    register_mcp_capabilities,
)
from .registry import (
    FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    CapabilityRegistry,
    boot_capability_registry,
)

__all__ = [
    "FRED_CAPABILITIES_ENTRY_POINT_GROUP",
    "MCP_CAPABILITY_SCHEMA_VERSION",
    "AssetSlotViolationError",
    "CapabilityAgentBlock",
    "McpCapability",
    "McpServerConfig",
    "build_mcp_capability",
    "register_mcp_capabilities",
    "CapabilityAssemblyError",
    "CapabilityConfigInvalidError",
    "CapabilityError",
    "CapabilityRegistrationError",
    "CapabilityRegistry",
    "CapabilityTableHygieneError",
    "DefaultOnRequiredSettingsError",
    "DuplicateCapabilityIdError",
    "DuplicateChatPartKindError",
    "MissingRequiredEnvError",
    "TurnOptionsInvalidError",
    "UnknownCapabilityError",
    "boot_capability_registry",
    "build_capability_agent_block",
    "build_capability_context",
    "build_capability_contexts",
    "evaluate_capability_chat_controls",
    "evaluate_chat_controls_batch",
    "enforce_asset_slots",
    "resolve_stored_config",
    "validate_turn_options",
]
