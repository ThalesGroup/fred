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

from control_plane_backend.kpi.presets.agent_prompt_length_distribution import (
    AGENT_PROMPT_LENGTH_DISTRIBUTION_PRESET,
)
from control_plane_backend.kpi.presets.agents_total import AGENTS_TOTAL_PRESET
from control_plane_backend.kpi.presets.analytics_activity_over_time import (
    ANALYTICS_ACTIVITY_OVER_TIME_PRESET,
)
from control_plane_backend.kpi.presets.analytics_adoption import (
    ANALYTICS_ADOPTION_PRESET,
)
from control_plane_backend.kpi.presets.analytics_agents import ANALYTICS_AGENTS_PRESET
from control_plane_backend.kpi.presets.analytics_overview import (
    ANALYTICS_OVERVIEW_PRESET,
)
from control_plane_backend.kpi.presets.analytics_quality_cost import (
    ANALYTICS_QUALITY_COST_PRESET,
)
from control_plane_backend.kpi.presets.analytics_teams import ANALYTICS_TEAMS_PRESET
from control_plane_backend.kpi.presets.analytics_teams_catalog import (
    ANALYTICS_TEAMS_CATALOG_PRESET,
)
from control_plane_backend.kpi.presets.analytics_usage import ANALYTICS_USAGE_PRESET
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.creation_assistant_usage import (
    CREATION_ASSISTANT_USAGE_PRESET,
)
from control_plane_backend.kpi.presets.sessions_over_time import (
    SESSIONS_OVER_TIME_PRESET,
)
from control_plane_backend.kpi.presets.skill_usage import (
    SKILL_USAGE_PRESET,
    USER_SKILL_USAGE_PRESET,
)
from control_plane_backend.kpi.presets.storage_by_team import STORAGE_BY_TEAM_PRESET
from control_plane_backend.kpi.presets.user_activity import (
    USER_AGENTS_USED_TOTAL_PRESET,
    USER_MESSAGES_TOTAL_PRESET,
    USER_SESSIONS_TOTAL_PRESET,
)
from control_plane_backend.kpi.presets.user_recent import (
    USER_RECENT_AGENTS_PRESET,
)
from control_plane_backend.kpi.presets.user_token_usage_by_agent import (
    USER_TOKEN_USAGE_BY_AGENT_PRESET,
)
from control_plane_backend.kpi.presets.user_token_usage_by_model import (
    USER_TOKEN_USAGE_BY_MODEL_PRESET,
)
from control_plane_backend.kpi.presets.user_token_usage_over_time import (
    USER_TOKEN_USAGE_OVER_TIME_PRESET,
)
from control_plane_backend.kpi.presets.user_top import (
    USER_TOP_AGENTS_PRESET,
    USER_TOP_TEAMS_PRESET,
)
from control_plane_backend.kpi.presets.web_research_summary import (
    WEB_RESEARCH_SUMMARY_PRESET,
)

PRESETS: list[PresetDef] = [
    SKILL_USAGE_PRESET,
    USER_SKILL_USAGE_PRESET,
    SESSIONS_OVER_TIME_PRESET,
    AGENTS_TOTAL_PRESET,
    AGENT_PROMPT_LENGTH_DISTRIBUTION_PRESET,
    USER_SESSIONS_TOTAL_PRESET,
    USER_MESSAGES_TOTAL_PRESET,
    USER_AGENTS_USED_TOTAL_PRESET,
    USER_TOP_AGENTS_PRESET,
    USER_TOP_TEAMS_PRESET,
    USER_RECENT_AGENTS_PRESET,
    USER_TOKEN_USAGE_OVER_TIME_PRESET,
    USER_TOKEN_USAGE_BY_AGENT_PRESET,
    USER_TOKEN_USAGE_BY_MODEL_PRESET,
    CREATION_ASSISTANT_USAGE_PRESET,
    STORAGE_BY_TEAM_PRESET,
    WEB_RESEARCH_SUMMARY_PRESET,
    ANALYTICS_TEAMS_CATALOG_PRESET,
    ANALYTICS_OVERVIEW_PRESET,
    ANALYTICS_ACTIVITY_OVER_TIME_PRESET,
    ANALYTICS_ADOPTION_PRESET,
    ANALYTICS_USAGE_PRESET,
    ANALYTICS_TEAMS_PRESET,
    ANALYTICS_AGENTS_PRESET,
    ANALYTICS_QUALITY_COST_PRESET,
]

__all__ = ["PRESETS", "PresetDef"]
