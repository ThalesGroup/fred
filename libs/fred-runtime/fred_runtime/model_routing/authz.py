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
Pod-side "which models may this team use" — the runtime enforcement half of
`kind="model"` capabilities (OBSERV-02 v3, `AGENT-CAPABILITY-RFC.md` §8.7).

**Deliberate small duplication, not a new pattern.** This mirrors
`control_plane_backend/capabilities/authz.py::usable_capability_ids` (and its
`_team_subject_and_context` helper) field-for-field — same OpenFGA relations,
same personal-team contextual-edge handling, same `CAN_USE`/`Resource.CAPABILITY`
check. It could not simply be imported: control-plane and fred-runtime are
separate deployables with no shared import path for control-plane-local code.
The right long-term fix is moving this query logic into `fred-core` (both
services already depend on it) so there is exactly one copy; that is real,
separate refactor scope against already-shipped, tested control-plane code,
deliberately not attempted under this branch's time budget — tracked in
`NOTES-OBSERV-02-FOLLOWUPS.md`.

Why this needs to exist AT ALL, unlike every other capability kind: `kind="tool"`/
`kind="agent"` enforcement happens entirely control-plane-side, at
prepare-execution and instance-suspension time (control-plane already knows the
instance's static `selected_capability_ids`). Model selection has no equivalent
static, persisted "selection" — `ModelRoutingResolver` resolves a profile
dynamically, per operation, inside one turn, and that resolution logic only
exists in fred-runtime (`models_catalog.yaml`, loaded pod-side). There is no
chokepoint in control-plane where "which model will this turn actually use" is
knowable in advance, so the check has to happen where the resolution happens.
"""

from __future__ import annotations

from fred_core import CapabilityPermission, RebacDisabledResult
from fred_core.common import is_personal_team_id
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
)
from fred_sdk.contracts.capability.manifest import MODEL_CAPABILITY_NAMESPACE_PREFIX


def _team_subject_and_context(team_id: str) -> tuple[RebacReference, list[Relation]]:
    """Team check subject + the contextual `organization#team` reverse edge.

    Identical to control-plane's helper of the same name — see module
    docstring for why this isn't a shared import.
    """
    team_ref = RebacReference(type=Resource.TEAM, id=team_id)
    org_ref = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)
    context = [Relation(subject=team_ref, relation=RelationType.TEAM, resource=org_ref)]
    if is_personal_team_id(team_id):
        context.append(
            Relation(
                subject=team_ref,
                relation=RelationType.PERSONAL_TEAM,
                resource=org_ref,
            )
        )
    return team_ref, context


async def usable_model_capability_ids(
    rebac: RebacEngine | None, team_id: str
) -> frozenset[str] | None:
    """`kind="model"` capability ids this team may use, computed ONCE per turn
    (never per model-routing resolution — see `_iterate_runtime_event_payloads`,
    the sole caller).

    Returns `None` when ReBAC is disabled/unconfigured — the existing
    dev/identity-only posture every other pod-side check already applies
    (`_authorize_execution_or_raise`): no restriction, not "restrict to
    nothing". A non-`None`, possibly-empty, frozenset means ReBAC is active
    and this is exactly what is allowed — `RoutedChatModelFactory` fails
    closed against it.
    """
    if rebac is None or not rebac.enabled:
        return None
    team_ref, context = _team_subject_and_context(team_id)
    refs = await rebac.lookup_resources(
        team_ref,
        CapabilityPermission.CAN_USE,
        Resource.CAPABILITY,
        contextual_relations=context,
    )
    if isinstance(refs, RebacDisabledResult):
        return None
    return frozenset(
        ref.id for ref in refs if ref.id.startswith(MODEL_CAPABILITY_NAMESPACE_PREFIX)
    )
