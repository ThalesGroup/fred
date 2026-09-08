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
Knowledge base contract (KNOWLEDGE-BASE-01, draft — see docs/swift/rfc/KNOWLEDGE-BASE-RFC.md).

Why this module has two objects, not one (RFC §2/§4, 2026-09-06 revision):
- A bare connector is too fine-grained to be the thing a developer brings to
  FRED — it says nothing on its own about what an agent can do with it. What
  a developer actually contributes, and what a platform admin actually
  enables, is a **`KnowledgeBaseType`**: a named, registered kind of
  knowledge base (`kind` + `mode` + `connector_kind`) — analogous to
  registering an agent template. It is platform-wide, not team-scoped.
- A **`KnowledgeBase`** is a team-scoped *instance* of an enabled
  `KnowledgeBaseType` — what a team creates once its type is enabled,
  carrying the team/tag scope and instance-specific connector configuration
  (e.g. which folder). This mirrors FRED's existing agent-template/
  agent-instance split; teams and admins already understand this shape.
- `scope` reuses the existing Team/Tag/ReBAC model completely — no new
  grouping primitive is introduced here.
- `mode` (push or pull) lives on `KnowledgeBaseType`, not `KnowledgeBase`: it
  is intrinsic to which type is being instantiated, not a per-instance
  choice — mutually exclusive on a given type, never both (see RFC §2/§7).
- `kind` names the pipeline/representation a knowledge base materializes.
  This module does not encode what a `kind` does with a change, or when —
  that decision belongs entirely to that pipeline's own code (see
  connector.py's docstring for the corresponding boundary on the connector
  side).
- `connector_kind` lives on `KnowledgeBaseType` (which connector
  implementation the type uses internally, e.g. `local_fs`) — it is what the
  usage-enablement check keys on (RFC §6), not implemented yet.
  `connector_ref` lives on the `KnowledgeBase` instance (the resolved
  instance config, e.g. a root path) and is deliberately not
  cross-validated against its `KnowledgeBaseType` here — whether it is
  required depends on a registry lookup this pure data contract does not
  own; that is a service-layer concern.

This is a pure data contract. No behavior, no registry, no factory — those are
deliberately deferred to the first proof-of-concept consumer, per the RFC's
own plan (§10), so the shape is validated against a real use before it is
extended.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class KnowledgeBaseMode(str, Enum):
    PUSH = "push"
    PULL = "pull"


class KnowledgeBaseKind(str, Enum):
    RAG_SQL = "rag_sql"
    GRAPHRAG = "graphrag"
    LLM_WIKI = "llm_wiki"
    SQL_LIVE = "sql_live"


class KnowledgeBaseType(FrozenModel):
    """
    A registered, platform-wide kind of knowledge base — what a developer
    brings to FRED and a platform admin enables per team (RFC §6). Not
    team-scoped.

    `connector_kind` is required if and only if `mode == PULL` — a push-mode
    type has no connector; a pull-mode type without one cannot be usage-gated.
    """

    knowledge_base_type_id: str = Field(
        min_length=1
    )  # e.g. "local_fs_rag" — the RFC §6 enablement key
    name: str = Field(min_length=1)
    kind: KnowledgeBaseKind
    mode: KnowledgeBaseMode
    connector_kind: str | None = None

    @model_validator(mode="after")
    def _connector_kind_matches_mode(self) -> "KnowledgeBaseType":
        if self.mode is KnowledgeBaseMode.PULL and not self.connector_kind:
            raise ValueError(
                "connector_kind is required when mode is KnowledgeBaseMode.PULL"
            )
        if self.mode is KnowledgeBaseMode.PUSH and self.connector_kind is not None:
            raise ValueError(
                "connector_kind must not be set when mode is KnowledgeBaseMode.PUSH"
            )
        return self


class KnowledgeBaseScope(FrozenModel):
    """Which documents belong to this knowledge base instance — an existing Team, optionally narrowed by Tags."""

    team_id: str = Field(min_length=1)
    tag_ids: list[str] = Field(default_factory=list)


class KnowledgeBase(FrozenModel):
    """
    A team-scoped instance of an enabled `KnowledgeBaseType`.

    `connector_ref` is the instance's own connector configuration (e.g. a
    root path or credentials reference) — opaque here, resolved by whatever
    code knows how to construct a `SourceConnector` for `knowledge_base_type_id`.
    """

    knowledge_base_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    knowledge_base_type_id: str = Field(min_length=1)
    scope: KnowledgeBaseScope
    connector_ref: str | None = None
