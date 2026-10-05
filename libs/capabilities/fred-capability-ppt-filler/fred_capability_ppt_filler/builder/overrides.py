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
    """Return ``(effective inventory, dropped override pattern ids)``; the
    input is not mutated. Runs every turn: only overridden patterns are copied,
    the others are shared with the (read-only) cached inventory."""
    dropped: List[str] = []
    by_id = {pattern.id: pattern for pattern in inventory.patterns}
    copies = {}

    for override in overrides:
        if override.pattern_id not in by_id:
            dropped.append(override.pattern_id)
            continue
        pattern = copies.get(override.pattern_id)
        if pattern is None:
            pattern = by_id[override.pattern_id].model_copy()
            copies[override.pattern_id] = pattern
        if override.label is not None and override.label.strip():
            pattern.label = override.label.strip()[:60]
        if override.kind is not None:
            pattern.kind = override.kind
        if override.included is not None:
            pattern.included = override.included
            pattern.exclusion_reason = None if override.included else "author"
    if not copies:
        return inventory, dropped
    patterns = [copies.get(p.id, p) for p in inventory.patterns]
    return inventory.model_copy(update={"patterns": patterns}), dropped


def prune_overrides(
    overrides: Sequence[PatternOverride], inventory: TemplateInventory
) -> Tuple[List[PatternOverride], List[str]]:
    """Keep only the overrides that still match ``inventory`` (after a re-upload)."""
    kept: List[PatternOverride] = []
    dropped: List[str] = []
    for override in overrides:
        if inventory.pattern(override.pattern_id) is None:
            dropped.append(override.pattern_id)
        else:
            kept.append(override)
    return kept, dropped
