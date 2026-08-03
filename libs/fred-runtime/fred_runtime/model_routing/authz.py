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

The team-subject `can_use` query itself
(`fred_core.security.rebac.capability_authz.usable_capability_ids`) is shared
with control-plane's `capabilities/authz.py`, which needs the exact same
query for its own catalog-listing/agent-save checks (2026-08-03, RSK-B
follow-up to #2191 — this file used to keep an independent, field-for-field
copy; see `NOTES-OBSERV-02-FOLLOWUPS.md` #16 for why that existed). This
module's own job is just the model-specific slice on top: tolerate `rebac is
None`, and filter the result down to `kind="model"` ids.

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

from fred_core import RebacEngine
from fred_core.security.rebac.capability_authz import (
    usable_capability_ids as _usable_capability_ids,
)
from fred_sdk.contracts.capability.manifest import MODEL_CAPABILITY_NAMESPACE_PREFIX


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
    ids = await _usable_capability_ids(rebac, team_id)
    if ids is None:
        return None
    return frozenset(
        cid for cid in ids if cid.startswith(MODEL_CAPABILITY_NAMESPACE_PREFIX)
    )
