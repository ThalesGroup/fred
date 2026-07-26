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
Regression guard for the §2.4 "Personal presets (Page 3)" gate: the three
`user_token_usage_*` presets must be `self_scoped` (so `resolve_kpi_scope`
skips OpenFGA — see `test_kpi_scope.py`) and never `team_scopable` (a
personal-usage preset accepting a `team_id` would defeat its own "my own
data" contract). Before this fix, none of the three declared `self_scoped`,
so the router's authorization chokepoint required `can_observe_platform` —
403ing any user who wasn't a platform admin/observer out of their own token
usage.
"""

from __future__ import annotations

from control_plane_backend.kpi.presets.user_token_usage_by_agent import (
    USER_TOKEN_USAGE_BY_AGENT_PRESET,
)
from control_plane_backend.kpi.presets.user_token_usage_by_model import (
    USER_TOKEN_USAGE_BY_MODEL_PRESET,
)
from control_plane_backend.kpi.presets.user_token_usage_over_time import (
    USER_TOKEN_USAGE_OVER_TIME_PRESET,
)

_PRESETS = [
    USER_TOKEN_USAGE_OVER_TIME_PRESET,
    USER_TOKEN_USAGE_BY_AGENT_PRESET,
    USER_TOKEN_USAGE_BY_MODEL_PRESET,
]


def test_user_token_usage_presets_are_self_scoped() -> None:
    for preset in _PRESETS:
        assert preset.self_scoped is True, preset.name


def test_user_token_usage_presets_are_not_team_scopable() -> None:
    for preset in _PRESETS:
        assert preset.team_scopable is False, preset.name
