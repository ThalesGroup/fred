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
Chat-controls evaluation wire contract (#1976, RFC §3.3, §3.7).

Why this module exists:
- session prep computes each agent instance's chat-time controls on the POD
  (capability code lives there, §7); control-plane asks the pod to evaluate
  `chat_controls(config)` over a BATCH of capabilities in one round-trip and
  caches the per-capability results cache-aside, keyed
  `(capability_id, manifest.version, config_hash)` — nothing derived persisted
- the request/response models are shared (fred-sdk) so control-plane parses the
  pod response with the SAME model, never a hand-declared copy — same rule as
  `CapabilityCatalogEntry`

How to use:
- control-plane: POST `ChatControlsRequest` to `/agents/capabilities/chat-controls`
  with only the cache-MISSED capabilities; merge `ChatControlsResponse.results`
  with cached items, then flatten into `ExecutionPreparation.chat_controls`
- pod: evaluate each item and return one `ChatControlsResult` per capability
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import StoredCapabilityConfig
from .manifest import ChatControlItem


class ChatControlsRequestItem(BaseModel):
    """One capability to evaluate: its id plus its verbatim stored slice."""

    capability_id: str = Field(min_length=1)
    # The stored envelope ({"schema_version", "config"}); None means "no stored
    # slice" — the pod evaluates against StoredConfigModel defaults, mirroring
    # execution-time assembly.
    config_envelope: StoredCapabilityConfig | None = None


class ChatControlsRequest(BaseModel):
    """Batch chat-controls evaluation request (control-plane → pod)."""

    items: list[ChatControlsRequestItem] = Field(default_factory=list)


class ChatControlsResult(BaseModel):
    """
    One capability's evaluated chat controls.

    `error` is non-None when the capability is not installed or its stored slice
    could not be resolved (RFC §3.9 `capability_config_invalid`); control-plane
    skips that capability with a warning rather than failing the whole prep.
    `manifest_version` is the pod's installed version — the authoritative value
    for the cache key — and is left empty on an error result (there is no
    version to cache under, and control-plane never caches an error).
    """

    capability_id: str = Field(min_length=1)
    manifest_version: str = ""
    controls: list[ChatControlItem] = Field(default_factory=list)
    error: str | None = None


class ChatControlsResponse(BaseModel):
    """Batch chat-controls evaluation response (pod → control-plane)."""

    results: list[ChatControlsResult] = Field(default_factory=list)
