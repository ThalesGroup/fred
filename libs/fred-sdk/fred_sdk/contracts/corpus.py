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
Indexed corpus contract (CORPUS-01, draft — see docs/swift/rfc/INDEXED-CORPUS-RFC.md).

Why this module exists:
- `Corpus` is FRED's central object for a named, independently-scoped,
  independently-typed unit of derived knowledge: `scope x mode x kind`.
- `scope` reuses the existing Team/Tag/ReBAC model completely — no new
  grouping primitive is introduced here.
- `mode` (push or pull) is mutually exclusive on a given corpus. A corpus is
  never fed by both at once — this is a deliberate simplicity choice, not an
  omission (see the RFC §2/§6).
- `kind` names the pipeline/representation a corpus materializes. This module
  does not encode what a `kind` does with a change, or when — that decision
  belongs entirely to that pipeline's own code (see connector.py's docstring
  for the corresponding boundary on the connector side).

This is a pure data contract. No behavior, no registry, no factory — those are
deliberately deferred to the first proof-of-concept consumer, per the RFC's
own plan (§9), so the shape is validated against a real use before it is
extended.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class CorpusMode(str, Enum):
    PUSH = "push"
    PULL = "pull"


class CorpusKind(str, Enum):
    RAG_SQL = "rag_sql"
    GRAPHRAG = "graphrag"
    LLM_WIKI = "llm_wiki"
    SQL_LIVE = "sql_live"


class CorpusScope(FrozenModel):
    """Which documents belong to this corpus — an existing Team, optionally narrowed by Tags."""

    team_id: str = Field(min_length=1)
    tag_ids: list[str] = Field(default_factory=list)


class Corpus(FrozenModel):
    """
    A named, scoped, typed unit of derived knowledge.

    `connector_ref` is required if and only if `mode == PULL` — a push-mode
    corpus has no connector, and a pull-mode corpus without one cannot be fed.
    """

    corpus_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scope: CorpusScope
    mode: CorpusMode
    kind: CorpusKind
    connector_ref: str | None = None

    @model_validator(mode="after")
    def _connector_ref_matches_mode(self) -> "Corpus":
        if self.mode is CorpusMode.PULL and not self.connector_ref:
            raise ValueError("connector_ref is required when mode is CorpusMode.PULL")
        if self.mode is CorpusMode.PUSH and self.connector_ref is not None:
            raise ValueError(
                "connector_ref must not be set when mode is CorpusMode.PUSH"
            )
        return self
