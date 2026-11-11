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

"""User filter of the platform analytics: access rule conditions evaluated on
the attributes platform access stores per user (`users.admission_attribute`,
last known value). Resolved to user ids by `resolve_kpi_scope` only."""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypeVar

from fastapi import HTTPException, Query
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    get_platform_access,
)
from fred_core.security.platform_access.rules import (
    evaluate,
    normalize_attribute,
    path_key,
)
from fred_core.users.user_models import UserRow
from fred_pod.security.platform_access import (
    PlatformAccessCondition,
    PlatformAccessPolicy,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

MAX_CONDITIONS = 8
# Keeps the encoded query string well under common proxy URL limits.
MAX_PARAM_LENGTH = 2000
# OpenSearch refuses a terms query above `index.max_terms_count` (65 536).
MAX_MATCHED_USERS = 50_000
SCAN_BUDGET_SECONDS = 5.0
CACHE_TTL_SECONDS = 60
CACHE_SIZE = 32

T = TypeVar("T")


# Annotated, so a direct call of a route function defaults to None.
UserFilterParam = Annotated[
    str | None,
    Query(
        description=(
            "Platform observers only: JSON {combination: all|any, conditions: "
            "[{claim, operator, value, case_sensitive}]} on the account attributes "
            f"platform access stores; at most {MAX_CONDITIONS} conditions and "
            f"{MAX_PARAM_LENGTH} characters. Restricts the figures to the matching users; "
            "rejected with 400 by presets that cannot be narrowed to users."
        ),
    ),
]


class AnalyticsUserFilter(BaseModel):
    """Conditions of the platform access rule, without its allow/block mode."""

    model_config = ConfigDict(extra="forbid")

    combination: Literal["all", "any"] = "all"
    conditions: list[PlatformAccessCondition] = Field(
        min_length=1, max_length=MAX_CONDITIONS
    )

    def policy(self) -> PlatformAccessPolicy:
        return PlatformAccessPolicy(
            combination=self.combination, conditions=self.conditions
        )

    def canonical(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class UserFilterMatch:
    """Matching user ids (sorted, never sent to the client) and the counts shown."""

    user_ids: tuple[str, ...]
    known_users: int
    no_data: int


@dataclass(frozen=True)
class ResolvedUserFilter:
    filter: AnalyticsUserFilter
    match: UserFilterMatch


class UserFilterField(BaseModel):
    claim: list[str]
    users: int = Field(description="Users with a stored value for this path.")
    in_rule: bool = Field(description="The current access rule uses this path.")


class UserFilterSummary(BaseModel):
    """Filterable attribute paths and, for a given filter, its coverage."""

    fields: list[UserFilterField]
    known_users: int
    matched: int | None = None
    no_data: int | None = None


def parse_user_filter(raw: str | None) -> AnalyticsUserFilter | None:
    if raw is None or not raw.strip():
        return None
    if len(raw) > MAX_PARAM_LENGTH:
        raise HTTPException(400, f"user_filter exceeds {MAX_PARAM_LENGTH} characters")
    try:
        return AnalyticsUserFilter.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(400, "invalid user_filter") from None


def match_users(
    user_filter: AnalyticsUserFilter,
    rows: Sequence[tuple[str, Mapping[str, Any] | None]],
) -> UserFilterMatch:
    """Pure and CPU-bound (regex): run it in a worker thread."""
    policy = user_filter.policy()
    deadline = time.monotonic() + SCAN_BUDGET_SECONDS
    matched: list[str] = []
    no_data = 0
    for user_id, attributes in rows:
        if time.monotonic() > deadline:
            raise HTTPException(400, "user_filter is too slow to evaluate")
        result = evaluate(policy, attributes or {})
        if "timeout" in result.reasons:
            raise HTTPException(400, "user_filter regular expression is too slow")
        if result.matched:
            matched.append(user_id)
        elif any(r in ("missing", "incompatible") for r in result.reasons):
            no_data += 1
    if len(matched) > MAX_MATCHED_USERS:
        raise HTTPException(
            400,
            f"user_filter matches more than {MAX_MATCHED_USERS} users: narrow it",
        )
    return UserFilterMatch(
        user_ids=tuple(sorted(matched)), known_users=len(rows), no_data=no_data
    )


def stored_fields(
    rows: Sequence[tuple[str, Mapping[str, Any] | None]],
    policy: PlatformAccessPolicy | None,
) -> list[UserFilterField]:
    counts: Counter[str] = Counter()
    for _, attributes in rows:
        counts.update(
            key
            for key, value in (attributes or {}).items()
            if normalize_attribute(value) is not None
        )
    in_rule = {path_key(c.claim) for c in policy.conditions} if policy else set()
    return sorted(
        (
            UserFilterField(
                claim=json.loads(key), users=counts[key], in_rule=key in in_rule
            )
            for key in counts.keys() | in_rule
        ),
        key=lambda f: (not f.in_rule, -f.users, f.claim),
    )


# (kind, filter, settings revision) -> (expiry, value). A per-pod performance
# cache only: every pod computes the same answer from the database.
_cache: dict[tuple[str, str, int], tuple[float, Any]] = {}
_lock = asyncio.Lock()


def _access() -> PlatformAccess:
    try:
        return get_platform_access()
    except HTTPException as error:
        if error.status_code == 404:
            raise HTTPException(
                400, "user_filter needs platform access to be installed"
            ) from None
        raise


async def _rows(
    access: PlatformAccess,
) -> tuple[PlatformAccessPolicy | None, list[tuple[str, Any]]]:
    """Every known identity with its stored attributes, in one statement."""
    async with access.store.read() as session:
        state = await access.state(session)
        rows = (
            await session.execute(
                select(UserRow.id, UserRow.admission_attribute).where(
                    UserRow.username.is_not(None)
                )
            )
        ).all()
    return access.policy(state), [(str(uid), attributes) for uid, attributes in rows]


async def _cached(
    kind: str, key: str, compute: Callable[[PlatformAccess], Awaitable[T]]
) -> T:
    access = _access()
    async with _lock:
        revision = (await access.state()).revision
        entry = _cache.get((kind, key, revision))
        if entry is not None and entry[0] > time.monotonic():
            return entry[1]
        value = await compute(access)
        if len(_cache) >= CACHE_SIZE:
            _cache.clear()
        _cache[(kind, key, revision)] = (time.monotonic() + CACHE_TTL_SECONDS, value)
        return value


async def resolve_user_filter(user_filter: AnalyticsUserFilter) -> UserFilterMatch:
    async def compute(access: PlatformAccess) -> UserFilterMatch:
        _, rows = await _rows(access)
        return await asyncio.to_thread(match_users, user_filter, rows)

    return await _cached("match", user_filter.canonical(), compute)


async def user_filter_fields() -> tuple[list[UserFilterField], int]:
    async def compute(access: PlatformAccess) -> tuple[list[UserFilterField], int]:
        policy, rows = await _rows(access)
        return await asyncio.to_thread(stored_fields, rows, policy), len(rows)

    return await _cached("fields", "", compute)


async def user_filter_summary(
    user_filter: AnalyticsUserFilter | None,
) -> UserFilterSummary:
    fields, known_users = await user_filter_fields()
    if user_filter is None:
        return UserFilterSummary(fields=fields, known_users=known_users)
    match = await resolve_user_filter(user_filter)
    return UserFilterSummary(
        fields=fields,
        known_users=match.known_users,
        matched=len(match.user_ids),
        no_data=match.no_data,
    )
