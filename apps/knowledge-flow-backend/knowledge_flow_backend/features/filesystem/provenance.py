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

"""Path-derived provenance for the agent filesystem (FILES-04 G4).

Why this exists:
- The Files UI shows where each file came from (deposé / généré / partagé). That
  signal is fully derivable from the virtual path area, because the FILES-04
  isolation rules make the path authoritative: only an agent writes its own
  agents subtree, only the owner writes their Mon espace, ingestion is the sole
  writer of the corpus. So v1 derives provenance from the path — no stored
  metadata, no migration (see AGENT-FILESYSTEM-RFC §8).

What is NOT derivable from the path alone:
- Inside `shared/` (Espace d'equipe), a directly-uploaded team file and a
  human share-copy are indistinguishable by path. In v1 there are no share-copies
  yet (G5 is not implemented), so `shared/` derives as `uploaded`. When G5 lands
  it stamps `shared_copy` + `shared_by`/`shared_at` on the one write it controls,
  refining this default.
- The uploader of a `shared/` file (no uid segment in the path) — left None.

Provenance is computed server-side from the authorized path; it is never taken
from client input.
"""

from __future__ import annotations

from dataclasses import dataclass

from knowledge_flow_backend.features.filesystem.virtual_fs_contract import (
    AREA_CORPUS,
    AREA_TEAMS,
    SUBAREA_AGENTS,
    SUBAREA_SHARED,
    SUBAREA_USERS,
    normalize_virtual_path,
)

# `origin` values (AGENT-FILESYSTEM-RFC §8).
ORIGIN_UPLOADED = "uploaded"
ORIGIN_AGENT_GENERATED = "agent_generated"
ORIGIN_SHARED_COPY = "shared_copy"
ORIGIN_INGESTED = "ingested"
ORIGIN_SYSTEM = "system"

# `producer` values.
PRODUCER_HUMAN = "human"
PRODUCER_INGESTION = "ingestion"


@dataclass(frozen=True)
class Provenance:
    """Immutable provenance for one filesystem object.

    `created_at` is intentionally absent: v1 has no in-place editing of agent
    outputs (RFC §6), so a file's `modified` timestamp is its creation time and
    the FsEntry already carries it. Add `created_at` only if editing lands.
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
    - `/teams/acme/users/u-1/notes.txt` -> uploaded, human, created_by `u-1`
    - `/teams/acme/shared/templates/brand.pptx` -> uploaded, human, created_by None
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

    if sub_area == SUBAREA_USERS:
        # teams/{team}/users/{uid}/...
        if len(parts) >= 4:
            return Provenance(origin=ORIGIN_UPLOADED, producer=PRODUCER_HUMAN, created_by=parts[3])
        return None

    if sub_area == SUBAREA_SHARED:
        # teams/{team}/shared/... — uploaded by default; G5 refines share-copies.
        return Provenance(origin=ORIGIN_UPLOADED, producer=PRODUCER_HUMAN, created_by=None)

    return None
