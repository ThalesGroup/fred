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
    # equivalent team-scoped store lookup exists) - set case by case, never
    # assumed. Otherwise the router rejects `team_ids` with 400 rather than
    # silently returning platform-wide data.
    team_scopable: bool = False
    # True only for the personal presets (§2.4 "Personal presets (Page 3)"):
    # the handler itself filters `WHERE dims.user_id = requesting_user.uid`,
    # so no OpenFGA check applies — any authenticated user may call it. Must
    # never be combined with `team_scopable=True`: the router rejects
    # `team_ids` for these the same way it does for any other
    # preset that isn't `team_scopable`.
    self_scoped: bool = False
    # Over-time presets: the router passes `bucket` (calendar unit, `auto` from
    # the period length) and `tz`. `zoned` passes only `tz`, for day-based maths.
    bucketable: bool = False
    zoned: bool = False
    # The router passes `user_ids` (platform user filter) and the handler MUST
    # apply `user_filter()` to every search; otherwise the router rejects one.
    user_filterable: bool = False
