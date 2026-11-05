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

from builder_decks import build_showcase_template
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.models import PatternOverride
from fred_capability_ppt_filler.builder.overrides import (
    apply_overrides,
    prune_overrides,
)


def _inventory():
    inventory = analyze_template(build_showcase_template()).inventory
    assert inventory is not None
    return inventory


def test_override_relabels_rekinds_and_excludes():
    inventory = _inventory()
    agenda = next(p for p in inventory.patterns if p.label == "Agenda")
    effective, dropped = apply_overrides(
        inventory,
        [
            PatternOverride(
                pattern_id=agenda.id,
                label="  Sommaire  ",
                kind="cards",
                included=False,
            )
        ],
    )
    assert dropped == []
    changed = effective.pattern(agenda.id)
    assert changed is not None
    assert (
        changed.label,
        changed.kind,
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


def test_unmatched_overrides_are_reported_not_applied():
    inventory = _inventory()
    effective, dropped = apply_overrides(
        inventory, [PatternOverride(pattern_id="slide:999", kind="cover")]
    )
    assert dropped == ["slide:999"]
    assert effective.pattern("layout:0").kind == inventory.pattern("layout:0").kind  # type: ignore[union-attr]


def test_prune_after_reupload_keeps_matching_overrides_only():
    inventory = _inventory()
    kept, dropped = prune_overrides(
        [
            PatternOverride(pattern_id="layout:0", label="Cover"),
            PatternOverride(pattern_id="slide:12345", included=False),
        ],
        inventory,
    )
    assert dropped == ["slide:12345"]
    assert [o.label for o in kept] == ["Cover"]


def test_zone_role_overrides_are_gone():
    """Stored configs written before the change still load: the old key is ignored."""
    override = PatternOverride.model_validate(
        {"pattern_id": "layout:0", "zone_roles": {"ph:0": "keep"}}
    )
    assert "zone_roles" not in override.model_dump()
