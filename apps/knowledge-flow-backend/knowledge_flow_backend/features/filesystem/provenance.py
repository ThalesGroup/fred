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

"""Path-derived provenance for corpus files and agent-generated outputs."""

from __future__ import annotations

from dataclasses import dataclass

from knowledge_flow_backend.features.filesystem.virtual_fs_contract import (
    AREA_CORPUS,
    AREA_TEAMS,
    SUBAREA_AGENTS,
    SUBAREA_USERS,
    normalize_virtual_path,
)

# `origin` values (FILES-04).
ORIGIN_AGENT_GENERATED = "agent_generated"
ORIGIN_INGESTED = "ingested"

# `producer` values.
PRODUCER_INGESTION = "ingestion"


@dataclass(frozen=True)
class Provenance:
    """Immutable provenance for one filesystem object.

    `created_at` is intentionally absent: v1 has no in-place editing of agent
    outputs (RFC §6), so a file's `modified` timestamp is its creation time and
    the response already carries it. Add `created_at` only if editing lands.
    """

    origin: str
    producer: str
    created_by: str | None


def derive_provenance(virtual_path: str) -> Provenance | None:
    """Derive provenance from a virtual path's area.

    Returns None for paths that carry no file-level provenance (root, a team box
    or sub-area directory with no owner segment yet, or an unknown area).

    Examples:
    - `/teams/acme/agents/inst-7/users/u-1/outputs/q3.pptx`
      -> agent_generated, producer `agent:inst-7`, created_by `u-1`
    - `/corpus/documents/doc-1/preview.md` -> ingested, ingestion, created_by None
    """
    normalized = normalize_virtual_path(virtual_path)
    if not normalized:
        return None
    parts = normalized.split("/")
    head = parts[0]

    if head == AREA_CORPUS:
        return Provenance(origin=ORIGIN_INGESTED, producer=PRODUCER_INGESTION, created_by=None)

    if head != AREA_TEAMS or len(parts) < 3:
        # `/teams` or `/teams/{team}` alone, or any non-team area: no file provenance.
        return None

    # parts: teams, {team}, {sub-area}, ...
    sub_area = parts[2]

    if sub_area == SUBAREA_AGENTS:
        # teams/{team}/agents/{agent_instance_id}/users/{uid}/...
        if len(parts) >= 6 and parts[4] == SUBAREA_USERS:
            return Provenance(
                origin=ORIGIN_AGENT_GENERATED,
                producer=f"agent:{parts[3]}",
                created_by=parts[5],
            )
        return None

    return None
