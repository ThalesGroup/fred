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

from control_plane_backend.kpi.presets.active_users_over_time import (
    ACTIVE_USERS_OVER_TIME_PRESET,
)
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.messages_over_time import (
    MESSAGES_OVER_TIME_PRESET,
)
from control_plane_backend.kpi.presets.sessions_over_time import (
    SESSIONS_OVER_TIME_PRESET,
)
from control_plane_backend.kpi.presets.unique_users_total import (
    UNIQUE_USERS_TOTAL_PRESET,
)

PRESETS: list[PresetDef] = [
    ACTIVE_USERS_OVER_TIME_PRESET,
    UNIQUE_USERS_TOTAL_PRESET,
    SESSIONS_OVER_TIME_PRESET,
    MESSAGES_OVER_TIME_PRESET,
]

__all__ = ["PRESETS", "PresetDef"]
