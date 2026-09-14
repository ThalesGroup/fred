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

"""Author overrides on top of an analysed inventory.

The inventory is what the analysis found; the overrides are the author's
corrections. Applying them yields the *effective* inventory the tool and the
form use. Overrides that no longer match (after a re-upload changed the
template) are reported, never silently kept.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from fred_capability_ppt_filler.builder.models import (
    PatternOverride,
    TemplateInventory,
)


def apply_overrides(
    inventory: TemplateInventory, overrides: Sequence[PatternOverride]
) -> Tuple[TemplateInventory, List[str]]:
    """Return ``(effective inventory, dropped override descriptions)``.

    The input is not mutated. A zone override whose key is gone drops only that
    zone entry; a pattern override whose pattern is gone drops entirely.
    """
    effective = inventory.model_copy(deep=True)
    dropped: List[str] = []
    by_id = {pattern.id: pattern for pattern in effective.patterns}

    for override in overrides:
        pattern = by_id.get(override.pattern_id)
        if pattern is None:
            dropped.append(override.pattern_id)
            continue
        if override.label is not None and override.label.strip():
            pattern.label = override.label.strip()[:60]
        if override.intent is not None:
            pattern.intent = override.intent
        if override.included is not None:
            pattern.included = override.included
            pattern.exclusion_reason = None if override.included else "author"
        if override.zone_roles:
            zones = {zone.key: zone for zone in pattern.zones}
            for group in pattern.groups:
                for item in group.items:
                    for zone in item:
                        zones[zone.key] = zone
            for key, role in override.zone_roles.items():
                zone = zones.get(key)
                if zone is None:
                    dropped.append(f"{override.pattern_id}/{key}")
                    continue
                zone.role = role
            for group in pattern.groups:
                # Item roles are per item position: refresh from the first
                # item so the tool description and the renderer agree.
                if group.items:
                    group.item_zones = [zone.role for zone in group.items[0]]
    return effective, dropped


def prune_overrides(
    overrides: Sequence[PatternOverride], inventory: TemplateInventory
) -> Tuple[List[PatternOverride], List[str]]:
    """Keep only the overrides that still match ``inventory`` (after a re-upload)."""
    kept: List[PatternOverride] = []
    dropped: List[str] = []
    for override in overrides:
        pattern = inventory.pattern(override.pattern_id)
        if pattern is None:
            dropped.append(override.pattern_id)
            continue
        keys = {zone.key for zone in pattern.zones}
        keys.update(
            zone.key
            for group in pattern.groups
            for item in group.items
            for zone in item
        )
        zone_roles = {}
        for key, role in override.zone_roles.items():
            if key in keys:
                zone_roles[key] = role
            else:
                dropped.append(f"{override.pattern_id}/{key}")
        kept.append(override.model_copy(update={"zone_roles": zone_roles}))
    return kept, dropped
