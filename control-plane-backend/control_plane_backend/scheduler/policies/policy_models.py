from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


MatchValue: TypeAlias = str | tuple[str, ...] | list[str]

# Supports a pragmatic subset used by lifecycle policies:
# weeks, days, hours, minutes, seconds (e.g. P7D, PT12H, PT0S).
_ISO8601_DURATION_RE = re.compile(
    r"^P(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso8601_duration(value: str) -> timedelta:
    raw = value.strip().upper()
    match = _ISO8601_DURATION_RE.fullmatch(raw)
    if not match:
        raise ValueError(
            "Unsupported ISO8601 duration format. "
            "Use weeks/days/hours/minutes/seconds (e.g. P7D, PT12H)."
        )

    if all(part is None for part in match.groupdict().values()):
        raise ValueError(
            "Unsupported ISO8601 duration format. "
            "At least one duration unit is required."
        )

    units = {name: int(part or 0) for name, part in match.groupdict().items()}
    if all(amount == 0 for amount in units.values()):
        return timedelta(0)

    return timedelta(
        weeks=units["weeks"],
        days=units["days"],
        hours=units["hours"],
        minutes=units["minutes"],
        seconds=units["seconds"],
    )


def duration_to_seconds(value: str) -> int:
    return int(parse_iso8601_duration(value).total_seconds())


def _validate_match_value(*, field_name: str, value: MatchValue | None) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string when provided")
        return
    if not value:
        raise ValueError(f"{field_name} must not be empty when provided")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")


class LifecycleTrigger(str, Enum):
    MEMBER_REMOVED = "member_removed"
    MEMBER_REJOINED = "member_rejoined"


class PurgeMode(str, Enum):
    DEFERRED_DELETE = "deferred_delete"
    IMMEDIATE_DELETE = "immediate_delete"


class ConversationLifecycleEvent(FrozenModel):
    conversation_id: str = Field(..., min_length=1)
    team_id: str | None = None
    trigger: LifecycleTrigger = LifecycleTrigger.MEMBER_REMOVED
    created_at: datetime
    last_activity_at: datetime

    @field_validator("created_at", "last_activity_at", mode="before")
    @classmethod
    def _coerce_dt(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            dt_value = value
        else:
            dt_value = datetime.fromisoformat(value)
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=timezone.utc)
        return dt_value


class PurgeMatch(FrozenModel):
    team_id: MatchValue | None = None
    trigger: MatchValue | None = None

    def defined_criteria_count(self) -> int:
        return sum(1 for value in (self.team_id, self.trigger) if value is not None)

    @model_validator(mode="after")
    def validate_match_values(self) -> "PurgeMatch":
        _validate_match_value(field_name="team_id", value=self.team_id)
        _validate_match_value(field_name="trigger", value=self.trigger)
        return self


class PolicyAction(FrozenModel):
    mode: PurgeMode = PurgeMode.DEFERRED_DELETE
    retention: str = Field(default="P7D", min_length=1)
    cancel_on_rejoin: bool = True

    @field_validator("retention")
    @classmethod
    def _validate_retention(cls, value: str) -> str:
        parse_iso8601_duration(value)
        return value

    @property
    def retention_seconds(self) -> int:
        return duration_to_seconds(self.retention)


class PolicyActionOverride(FrozenModel):
    mode: PurgeMode | None = None
    retention: str | None = Field(default=None, min_length=1)
    cancel_on_rejoin: bool | None = None

    @field_validator("retention")
    @classmethod
    def _validate_retention(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parse_iso8601_duration(value)
        return value


class PolicyRule(FrozenModel):
    rule_id: str = Field(..., min_length=1)
    match: PurgeMatch = Field(default_factory=PurgeMatch)
    action: PolicyActionOverride = Field(default_factory=PolicyActionOverride)


class PurgePolicy(FrozenModel):
    default: PolicyAction = Field(default_factory=PolicyAction)
    rules: tuple[PolicyRule, ...] = ()


class ConversationPolicies(FrozenModel):
    purge: PurgePolicy = Field(default_factory=PurgePolicy)


class ConversationPolicyCatalog(FrozenModel):
    version: Literal["v1"] = "v1"
    conversation_policies: ConversationPolicies = Field(
        default_factory=ConversationPolicies
    )


class PolicyEvaluationResult(BaseModel):
    mode: PurgeMode
    retention: str
    retention_seconds: int
    cancel_on_rejoin: bool
    matched_rule_id: str | None = None
    matched_rule_specificity: int = 0


class PolicyResolutionRequest(BaseModel):
    team_id: str | None = None
    trigger: LifecycleTrigger = LifecycleTrigger.MEMBER_REMOVED


def default_conversation_policy_catalog() -> ConversationPolicyCatalog:
    return ConversationPolicyCatalog()
