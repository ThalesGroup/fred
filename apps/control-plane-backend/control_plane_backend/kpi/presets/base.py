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

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from pydantic import BaseModel


@dataclass
class PresetDef:
    name: str
    response_model: type[BaseModel]
    handler: Callable[..., Coroutine[Any, Any, BaseModel]]
    summary: str
    # True only when the underlying KPI event carries a `dims.team_id` (or an
    # equivalent team-scoped store lookup exists) — set case by case, never
    # assumed. A preset whose source event has no team_id (e.g. the generic
    # HTTP middleware's `api.request_latency_ms`, by design — see
    # `KPI-ANALYTICS-RFC.md` §2.2) or that is inherently cross-team (e.g.
    # `top_teams_by_sessions`) stays False; the router (`api.py`) rejects a
    # `team_id` query param for it with 400 rather than silently ignoring it.
    team_scopable: bool = False
    # True only for the platform-wide admin section's presets (§2.4/§2.5 —
    # `storage_by_team`/`team_activity_summary` at org scope): the router
    # requires `can_manage_platform` instead of the usual `can_observe_platform`
    # when `team_id` is None. Never affects the team-scoped check
    # (`can_read_members`), which applies uniformly regardless of this flag.
    platform_admin_only: bool = False
