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

from pathlib import Path

import pytest

from control_plane_backend.core.policies.catalog import (
    load_conversation_policy_catalog,
)
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.scheduler.policies.retention_resolver import (
    resolve_team_retention,
    resolve_team_retention_view,
)

# The shipped default catalog that ships with the control-plane backend.
_SHIPPED_CATALOG = (
    Path(__file__).resolve().parents[1] / "config" / "conversation_policy_catalog.yaml"
)

# Each case is applied to both governed fields (team_delete_grace, max_idle):
# the clamp is field-agnostic, so one parametrized suite proves both.


def test_no_team_value_inherits_platform_cap() -> None:
    res = resolve_team_retention(platform_max="P30D", team_value=None)
    assert res.effective == "P30D"
    assert res.source == "platform"
    assert res.would_exceed is False
    assert res.platform_max == "P30D"
    assert res.team_value is None


def test_team_value_below_cap_is_taken() -> None:
    res = resolve_team_retention(platform_max="P30D", team_value="P7D")
    assert res.effective == "P7D"
    assert res.source == "team"
    assert res.would_exceed is False


def test_team_value_equal_to_cap_is_team_source() -> None:
    res = resolve_team_retention(platform_max="P30D", team_value="P30D")
    assert res.effective == "P30D"
    assert res.source == "team"
    assert res.would_exceed is False


def test_team_value_above_cap_is_clamped_and_flagged() -> None:
    res = resolve_team_retention(platform_max="P7D", team_value="P30D")
    # Clamped down to the cap; B5 PATCH turns would_exceed into a 422.
    assert res.effective == "P7D"
    assert res.source == "platform"
    assert res.would_exceed is True


def test_equal_durations_different_strings_keep_team_original() -> None:
    # P1D and PT24H are equal in seconds; team value (<= cap) is returned as-is,
    # never recomputed to a canonical ISO form.
    res = resolve_team_retention(platform_max="P1D", team_value="PT24H")
    assert res.effective == "PT24H"
    assert res.source == "team"
    assert res.would_exceed is False


def test_platform_max_none_rejects_team_value() -> None:
    # Edge case: no platform cap configured for this field. A team value is
    # REJECTED (would_exceed → 422), not accepted unbounded — retention cannot be
    # loosened without a platform-set ceiling.
    res = resolve_team_retention(platform_max=None, team_value="P90D")
    assert res.effective is None
    assert res.source == "platform"
    assert res.would_exceed is True
    assert res.platform_max is None
    assert res.team_value == "P90D"


def test_platform_max_none_and_team_value_none_is_unset() -> None:
    res = resolve_team_retention(platform_max=None, team_value=None)
    assert res.effective is None
    assert res.source == "platform"
    assert res.would_exceed is False


def _purge_policy(*, default_grace: str, default_idle: str):
    catalog = ConversationPolicyCatalog.model_validate(
        {
            "conversation_policies": {
                "purge": {
                    "default": {
                        "team_delete_grace": default_grace,
                        "max_idle": default_idle,
                    },
                    "rules": [
                        {
                            "rule_id": "purge.team.swiftpost",
                            "match": {"team_id": "swiftpost"},
                            "action": {"team_delete_grace": "P14D"},
                        }
                    ],
                }
            }
        }
    )
    return catalog.conversation_policies.purge


def test_view_no_override_inherits_platform_for_both_fields() -> None:
    view = resolve_team_retention_view(
        policy=_purge_policy(default_grace="P30D", default_idle="P60D"),
        team_id="northbridge",
        team_delete_grace_override=None,
        max_idle_override=None,
    )
    assert view.team_delete_grace.effective == "P30D"
    assert view.team_delete_grace.source == "platform"
    assert view.max_idle.effective == "P60D"
    assert view.max_idle.source == "platform"


def test_view_uses_per_team_cap_from_specificity() -> None:
    # The swiftpost rule tightens the grace cap to P14D; the override (P7D) is
    # below that resolved cap, so it is accepted.
    view = resolve_team_retention_view(
        policy=_purge_policy(default_grace="P30D", default_idle="P60D"),
        team_id="swiftpost",
        team_delete_grace_override="P7D",
        max_idle_override="P90D",
    )
    assert view.team_delete_grace.platform_max == "P14D"
    assert view.team_delete_grace.effective == "P7D"
    assert view.team_delete_grace.source == "team"
    # max_idle override (P90D) exceeds the default cap (P60D) → clamped.
    assert view.max_idle.platform_max == "P60D"
    assert view.max_idle.effective == "P60D"
    assert view.max_idle.would_exceed is True


def test_view_override_above_team_cap_is_clamped() -> None:
    view = resolve_team_retention_view(
        policy=_purge_policy(default_grace="P30D", default_idle="P60D"),
        team_id="swiftpost",
        team_delete_grace_override="P30D",  # exceeds the P14D per-team cap
        max_idle_override=None,
    )
    assert view.team_delete_grace.effective == "P14D"
    assert view.team_delete_grace.source == "platform"
    assert view.team_delete_grace.would_exceed is True


@pytest.mark.parametrize(
    ("platform_max", "team_value", "effective", "source", "would_exceed"),
    [
        ("P30D", None, "P30D", "platform", False),
        ("P30D", "P7D", "P7D", "team", False),
        ("P30D", "P30D", "P30D", "team", False),
        ("P7D", "P30D", "P7D", "platform", True),
        # No cap + team value → rejected (effective unset, would_exceed → 422).
        (None, "P90D", None, "platform", True),
        (None, None, None, "platform", False),
    ],
)
def test_resolve_team_retention_table(
    platform_max: str | None,
    team_value: str | None,
    effective: str | None,
    source: str,
    would_exceed: bool,
) -> None:
    res = resolve_team_retention(platform_max=platform_max, team_value=team_value)
    assert res.effective == effective
    assert res.source == source
    assert res.would_exceed == would_exceed


def test_shipped_catalog_defines_platform_caps() -> None:
    # Regression guard (Codex gap): the SHIPPED catalog must define both governed
    # caps, else the "team may only tighten" guarantee is off in production and
    # every team override is rejected. Runs the real yaml, not an injected one.
    purge = load_conversation_policy_catalog(
        _SHIPPED_CATALOG
    ).conversation_policies.purge
    view = resolve_team_retention_view(
        policy=purge,
        team_id="some-team",
        team_delete_grace_override=None,
        max_idle_override=None,
    )
    assert view.team_delete_grace.platform_max is not None
    assert view.max_idle.platform_max is not None


def test_shipped_catalog_bounds_a_too_long_team_override() -> None:
    # With the shipped caps present, a team value longer than the cap is clamped
    # and flagged (→ 422), not accepted — proving the guardrail is live end-to-end
    # against the real catalog file.
    purge = load_conversation_policy_catalog(
        _SHIPPED_CATALOG
    ).conversation_policies.purge
    view = resolve_team_retention_view(
        policy=purge,
        team_id="some-team",
        team_delete_grace_override="P3650D",  # ~10 years, far above any sane cap
        max_idle_override=None,
    )
    assert view.team_delete_grace.would_exceed is True
    assert view.team_delete_grace.source == "platform"
