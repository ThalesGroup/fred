"""Per-team retention resolver (CTRLP-12 B3).

Resolves, for a single retention field, the effective value a team gets given
the platform cap and the team's own override — under the RFC §3.B rule
**platform caps, team may only tighten**.

The clamp (:func:`resolve_team_retention`) is a *pure* function: no I/O, no
store access. It only compares two ISO-8601 duration strings (via
``duration_to_seconds``) and returns one of the *original* strings — never a
duration recomputed back to ISO — so the smallest input representation is
preserved exactly.

The thin wrapper (:func:`resolve_team_retention_view`) applies the clamp to both
governed fields (``team_delete_grace`` and ``max_idle``) using
``evaluate_purge_policy`` for the caps. It stays pure too: the caller (B4/B5)
does the store read and passes the override strings in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from control_plane_backend.scheduler.policies.policy_engine import (
    evaluate_purge_policy,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
    PurgePolicy,
    duration_to_seconds,
)

RetentionSource = Literal["platform", "team"]


@dataclass(frozen=True)
class FieldRetentionResolution:
    """Resolved view of one retention field for one team.

    - ``platform_max``: the platform cap (None = no cap configured).
    - ``team_value``: the team's override (None = team set nothing).
    - ``effective``: the value that actually applies (one of the two originals).
    - ``source``: ``"team"`` if the team value applies, else ``"platform"``.
    - ``would_exceed``: True only when the team asked for *more* than the cap;
      the value is clamped down to the cap and B5's PATCH turns this into a 422.
    """

    platform_max: str | None
    team_value: str | None
    effective: str | None
    source: RetentionSource
    would_exceed: bool = False


def resolve_team_retention(
    *, platform_max: str | None, team_value: str | None
) -> FieldRetentionResolution:
    """Clamp one team retention value to the platform cap (team may only tighten).

    Rules:
    - ``team_value`` None → inherit the platform cap (``source="platform"``).
    - ``team_value`` <= ``platform_max`` → take the team value (``source="team"``).
    - ``team_value`` > ``platform_max`` → clamp to the cap (``source="platform"``,
      ``would_exceed=True``).

    Edge case — **``platform_max`` is None** (the catalog configured no cap for
    this field): there is nothing to clamp against, so the **team value is taken
    as-is** (``source="team"``, ``would_exceed=False``). If both are None, the
    field is simply unset (``effective=None``, ``source="platform"``).

    Pure: no I/O. ``effective`` is always one of the two original strings, never
    a recomputed duration.
    """
    # Team set nothing → inherit the platform cap (possibly None).
    if team_value is None:
        return FieldRetentionResolution(
            platform_max=platform_max,
            team_value=None,
            effective=platform_max,
            source="platform",
        )

    # No platform cap configured → nothing to clamp against; take team as-is.
    if platform_max is None:
        return FieldRetentionResolution(
            platform_max=None,
            team_value=team_value,
            effective=team_value,
            source="team",
        )

    # Both set → team may only tighten (<= cap).
    if duration_to_seconds(team_value) <= duration_to_seconds(platform_max):
        return FieldRetentionResolution(
            platform_max=platform_max,
            team_value=team_value,
            effective=team_value,
            source="team",
        )

    # Team asked for more than the cap → clamp down; B5 raises 422 on this flag.
    return FieldRetentionResolution(
        platform_max=platform_max,
        team_value=team_value,
        effective=platform_max,
        source="platform",
        would_exceed=True,
    )


@dataclass(frozen=True)
class TeamRetentionResolution:
    """Resolved view of both governed retention fields for one team."""

    team_delete_grace: FieldRetentionResolution
    max_idle: FieldRetentionResolution


def resolve_team_retention_view(
    *,
    policy: PurgePolicy,
    team_id: str | None,
    team_delete_grace_override: str | None,
    max_idle_override: str | None,
    trigger: str = LifecycleTrigger.MEMBER_REMOVED.value,
) -> TeamRetentionResolution:
    """Resolve ``team_delete_grace`` and ``max_idle`` for one team.

    Reuses ``evaluate_purge_policy`` to obtain the platform caps with the same
    per-team specificity as the rest of the policy engine (no re-matching here),
    then clamps each field via :func:`resolve_team_retention`.

    Pure: the override strings are passed in by the caller (which owns the store
    read), so this function performs no I/O.
    """
    caps = evaluate_purge_policy(policy, team_id=team_id, trigger=trigger)
    return TeamRetentionResolution(
        team_delete_grace=resolve_team_retention(
            platform_max=caps.team_delete_grace,
            team_value=team_delete_grace_override,
        ),
        max_idle=resolve_team_retention(
            platform_max=caps.max_idle,
            team_value=max_idle_override,
        ),
    )
