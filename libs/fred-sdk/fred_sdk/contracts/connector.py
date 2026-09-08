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
Source connector contract (KNOWLEDGE-BASE-01, draft — see docs/swift/rfc/KNOWLEDGE-BASE-RFC.md).

Why this module exists:
- A connector's job is narrow and deliberately kept that way: discover
  changes at a remote source, and fetch the artifact for one of them. Nothing
  else. It must never know which `KnowledgeBaseKind` (knowledge_base.py)
  consumes its output, and it must never decide batching, scheduling, or
  reprocessing granularity — that is entirely the knowledge base pipeline's
  decision.
- `source_item_id` and `revision` are two distinct, provider-defined, stable
  fields — never derived from a display path or a mutable timestamp. This is
  the direct fix for the concrete failure mode this RFC was written against:
  a real FRED connector (Sphere) diffed by a raw modified-timestamp string,
  had no stable identity, and turned every rename into a delete+add. Keeping
  identity and revision stable and separate makes a rename representable and
  makes "nothing changed" cheaply provable without re-fetching content.
- `DELETE` is a first-class `ChangeKind`, not something the caller has to
  infer by diffing two listings itself.

`SourceConnector` must stay importable with no dependency beyond pydantic and
the standard library — no Temporal types, no database/store implementations,
no Knowledge Flow application models. `tests/test_sdk_purity.py` enforces the
transitive-import side of this boundary at the package level.

This is a pure data + protocol contract. No behavior, no registry, no
implementation — those are deliberately deferred to the first
proof-of-concept connector, per the RFC's own plan (§9).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ChangeKind(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"


class SourceItem(FrozenModel):
    """One item at the remote source, identified independently of its display path."""

    source_item_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    display_path: str = Field(min_length=1)
    size_bytes: int | None = None
    modified_at: datetime | None = None


class SourceChange(FrozenModel):
    item: SourceItem
    kind: ChangeKind


class SourceConnector(Protocol):
    """
    Discover/fetch surface a knowledge base in pull mode is fed through.

    Implementations own the credentials and remote API calls; they own
    nothing about how a change is applied downstream.
    """

    def discover_changes(self, cursor: str | None) -> tuple[list[SourceChange], str]:
        """
        Return a bounded batch of changes since `cursor`, plus the next cursor.

        Must never require the caller to have accepted the returned batch
        before returning it — advancing the durable cursor past changes the
        caller has not durably accepted is a caller-side responsibility, not
        this method's.
        """
        ...

    def fetch(self, item: SourceItem, destination_dir: Path) -> Path:
        """Download the artifact identified by `item` (at `item.revision`) into `destination_dir`."""
        ...
