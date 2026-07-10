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
Capability manifest — the declaration half of a capability (#1973, RFC §3.1).

Why this module exists:
- one declarative object drives the product contract and the generated UI:
  agent-creation fields, upload slots, contributed chat parts and side panels,
  the capability router, owned tables, required env vars, and team scoping
- the runtime registry (fred-runtime) validates manifests at pod boot and
  fails startup loudly on conflicts (RFC §4)

How to use:
- declare one `CapabilityManifest` as the `manifest` ClassVar of an
  `AgentCapability` subclass; keep `version` bumped per release — it is the
  cache key for computed surfaces (RFC §3.7) and the stored-config schema
  version (RFC §3.9)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import FieldSpec


class TeamScopePolicy(str, Enum):
    """How a capability becomes usable by a team (RFC §7, §8.3)."""

    DEFAULT_ON = "default_on"
    ADMIN_GATED = "admin_gated"


class UploadedFile(BaseModel):
    """One uploaded asset binary handed to `validate_config` (RFC §3.4)."""

    filename: str
    content: bytes


class AssetSlot(BaseModel):
    """
    One named upload slot on the agent-creation form (RFC §3.4).

    Why this exists:
    - `min_count`/`max_count` covers "exactly one .pptx", "up to N reference
      PDFs", and mixed cases with several slots — no special mechanism
    - the platform enforces cardinality and extension per slot BEFORE calling
      the capability; `validate_config` only owns content validation
    """

    key: str = Field(min_length=1)
    accepted_types: list[str]
    min_count: int = Field(default=0, ge=0)
    max_count: int | None = 1

    @model_validator(mode="after")
    def _check_cardinality(self) -> "AssetSlot":
        if self.max_count is not None and self.max_count < max(1, self.min_count):
            raise ValueError(
                f"AssetSlot '{self.key}': max_count={self.max_count} must be None "
                f"(unbounded) or >= max(1, min_count={self.min_count})."
            )
        return self


class ChatControlSpec(BaseModel):
    """
    One computed chat-time control descriptor (RFC §3.3).

    How to use:
    - `widget` is resolved against the composer-control registry; unknown ids
      are silently skipped by the frontend (forward-compatible)
    - list order returned by `AgentCapability.chat_controls` = display order
    """

    widget: str = Field(min_length=1)
    params: BaseModel | None = None


class SidePanelSpec(BaseModel):
    """One side panel a capability mounts beside the chat (RFC §3.1)."""

    widget: str = Field(min_length=1)
    params: BaseModel | None = None


def chat_part_kind(part: type[BaseModel]) -> str:
    """
    Extract the discriminator value of one contributed chat part (RFC §3.6).

    Why this exists:
    - chat parts extend the `UiPart` union, discriminated on the `type` field
      (`LinkPart.type = "link"`, `GeoPart.type = "geo"`); the runtime registry
      must reject duplicate discriminators at boot to keep the union
      unambiguous

    How to use:
    - declare the part with `type: Literal["<kind>"] = "<kind>"`
    """

    field_info = part.model_fields.get("type")
    if field_info is None:
        raise ValueError(
            f"Chat part {part.__name__} has no 'type' discriminator field; "
            'declare it as `type: Literal["<kind>"] = "<kind>"`.'
        )
    annotation = field_info.annotation
    args = get_args(annotation)
    if (
        get_origin(annotation) is Literal
        and len(args) == 1
        and isinstance(args[0], str)
    ):
        return args[0]
    if isinstance(field_info.default, str) and field_info.default:
        return field_info.default
    raise ValueError(
        f"Chat part {part.__name__} must declare 'type' as a single-value "
        "string Literal (the chat-part kind)."
    )


class CapabilityManifest(BaseModel):
    """
    The declaration half of a capability (RFC §3.1).

    Notes:
    - `router` is a FastAPI `APIRouter` (typed `Any` — fred-sdk does not
      depend on fastapi); auto-mounted under `/capabilities/{id}/...` (§9.1)
    - `tables` are SQLAlchemy `DeclarativeBase` subclasses (typed `Any` —
      fred-sdk does not depend on sqlalchemy); migrations ship with the
      package (§7.1)
    - `state_models` opts typed (pydantic) capability state channels into the
      checkpointer msgpack allowlist at registration; JSON-primitive channels
      need no entry (§5.2 spike rule, #1971)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1, description="i18n key")
    description: str = Field(min_length=1, description="i18n key")
    icon: str = Field(min_length=1)

    config_fields: list[FieldSpec] = Field(default_factory=list)
    assets: list[AssetSlot] = Field(default_factory=list)
    chat_parts: list[type[BaseModel]] = Field(default_factory=list)
    side_panels: list[SidePanelSpec] = Field(default_factory=list)

    router: Any | None = None
    tables: list[Any] = Field(default_factory=list)
    required_env: list[str] = Field(default_factory=list)
    state_models: list[type[BaseModel]] = Field(default_factory=list)

    team_scope: TeamScopePolicy = TeamScopePolicy.ADMIN_GATED
