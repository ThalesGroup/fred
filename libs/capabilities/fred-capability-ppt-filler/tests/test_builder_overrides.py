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

from __future__ import annotations

from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.models import PatternOverride
from fred_capability_ppt_filler.builder.overrides import (
    apply_overrides,
    prune_overrides,
)
from builder_decks import build_showcase_template


def _inventory():
    inventory = analyze_template(build_showcase_template()).inventory
    assert inventory is not None
    return inventory


def test_override_relabels_reintents_and_excludes():
    inventory = _inventory()
    agenda = next(p for p in inventory.patterns if p.label == "Agenda")
    effective, dropped = apply_overrides(
        inventory,
        [
            PatternOverride(
                pattern_id=agenda.id,
                label="  Sommaire  ",
                intent="cards",
                included=False,
            )
        ],
    )
    assert dropped == []
    changed = effective.pattern(agenda.id)
    assert changed is not None
    assert (
        changed.label,
        changed.intent,
        changed.included,
        changed.exclusion_reason,
    ) == (
        "Sommaire",
        "cards",
        False,
        "author",
    )
    # The source inventory is untouched.
    assert agenda.label == "Agenda" and agenda.included


def test_zone_role_override_reaches_group_items_and_refreshes_item_roles():
    inventory = _inventory()
    kpi = next(p for p in inventory.patterns if p.label == "Key figures")
    label_key = kpi.groups[0].items[0][1].key
    effective, dropped = apply_overrides(
        inventory, [PatternOverride(pattern_id=kpi.id, zone_roles={label_key: "keep"})]
    )
    assert dropped == []
    group = effective.pattern(kpi.id).groups[0]  # type: ignore[union-attr]
    assert group.items[0][1].role == "keep"
    assert group.item_zones == ["number", "keep"]


def test_unmatched_overrides_are_reported_not_applied():
    inventory = _inventory()
    effective, dropped = apply_overrides(
        inventory,
        [
            PatternOverride(pattern_id="slide:999", intent="title"),
            PatternOverride(pattern_id="layout:0", zone_roles={"ph:42": "keep"}),
        ],
    )
    assert dropped == ["slide:999", "layout:0/ph:42"]
    assert effective.pattern("layout:0").intent == inventory.pattern("layout:0").intent  # type: ignore[union-attr]


def test_prune_after_reupload_keeps_matching_overrides_only():
    inventory = _inventory()
    kept, dropped = prune_overrides(
        [
            PatternOverride(
                pattern_id="layout:0",
                label="Cover",
                zone_roles={"ph:0": "keep", "ph:9": "body"},
            ),
            PatternOverride(pattern_id="slide:12345", included=False),
        ],
        inventory,
    )
    assert dropped == ["layout:0/ph:9", "slide:12345"]
    assert len(kept) == 1
    assert kept[0].label == "Cover" and kept[0].zone_roles == {"ph:0": "keep"}
