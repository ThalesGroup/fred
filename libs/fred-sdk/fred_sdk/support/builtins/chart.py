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

"""Bounded, self-contained results for native chat charts."""

from __future__ import annotations

import json
import math
import re
from typing import Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from fred_sdk.contracts.builtin_tool_refs import TOOL_REF_CHART_RENDER
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
    UiPart,
)

ChartType = Literal[
    "bar",
    "bar_horizontal",
    "bar_stacked",
    "line",
    "area",
    "area_stacked",
    "pie",
    "donut",
    "scatter",
    "radar",
    "radial_bar",
    "funnel",
    "treemap",
    "composed",
    "table",
]
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")
_SINGLE_NONNEGATIVE = {"pie", "donut", "radial_bar", "funnel", "treemap"}
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _group_identity(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError("Grouped bar keys must be safe finite numbers.") from exc
        if not math.isfinite(number) or abs(number) > _MAX_SAFE_INTEGER:
            raise ValueError("Grouped bar keys must be safe finite numbers.")
        value = 0 if number == 0 else number
    return json.dumps(value, ensure_ascii=False)


class ChartRenderToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_type: ChartType = Field(
        description=(
            "View: bar/bar_horizontal for category comparison; bar_stacked for parts of totals; "
            "line/area for ordered trends; area_stacked for cumulative trends; "
            "pie/donut for a few shares; scatter for numeric x/y correlation; "
            "radar for category profiles; radial_bar for ranked nonnegative values; "
            "funnel for ordered stages; treemap for relative sizes; composed for a bar series "
            "plus line series; table for details. Histogram bins use bar."
        )
    )
    title: str = Field(min_length=1, max_length=120)
    rows: list[dict[str, StrictStr | StrictInt | StrictFloat | StrictBool | None]] = (
        Field(
            min_length=1,
            max_length=50,
            description="Actual rows returned by a data tool, with JSON scalar values.",
        )
    )
    x_key: str | None = None
    y_keys: list[str] = Field(default_factory=list, max_length=8)
    group_key: str | None = Field(
        default=None,
        description="For grouped bars in long-form rows, the column naming each bar group.",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_oversized_rows(cls, payload: object) -> object:
        if not isinstance(payload, dict):
            return payload
        rows = payload.get("rows")
        if not isinstance(rows, list):
            return payload
        size = 0
        for row in rows[:51]:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if isinstance(key, str):
                    size += len(key)
                if isinstance(value, str):
                    size += len(value)
                if size > 50_000:
                    raise ValueError(
                        "Chart payload exceeds 50,000 serialized characters."
                    )
        return payload

    @model_validator(mode="after")
    def validate_chart(self) -> "ChartRenderToolArgs":
        if not self.title.strip():
            raise ValueError("Chart title must not be blank.")
        if self.chart_type == "table" and self.group_key is not None:
            raise ValueError("group_key is only supported for bar charts.")
        for row in self.rows:
            if any(
                isinstance(value, int)
                and not isinstance(value, bool)
                and abs(value) > _MAX_SAFE_INTEGER
                for value in row.values()
            ):
                raise ValueError("Chart rows must contain JavaScript-safe integers.")
            if any(
                isinstance(value, float) and not math.isfinite(value)
                for value in row.values()
            ):
                raise ValueError("Chart rows must contain finite JSON scalar values.")
        if self.chart_type != "table":
            if not self.x_key or not self.y_keys:
                raise ValueError("Plotted charts require x_key and y_keys.")
            if len(set(self.y_keys)) != len(self.y_keys):
                raise ValueError("y_keys must be distinct.")
            if (
                self.chart_type in _SINGLE_NONNEGATIVE | {"scatter"}
                and len(self.y_keys) != 1
            ):
                raise ValueError(f"{self.chart_type} charts require exactly one y_key.")
            if self.chart_type == "composed" and len(self.y_keys) < 2:
                raise ValueError("Composed charts require at least two y_keys.")
            if self.group_key is not None and (
                self.chart_type not in {"bar", "bar_horizontal", "bar_stacked"}
                or len(self.y_keys) != 1
                or not self.group_key
                or self.group_key in {self.x_key, self.y_keys[0]}
            ):
                raise ValueError(
                    "group_key requires a distinct column and one bar series."
                )
            seen_groups: set[str] = set()
            group_values: set[str] = set()
            for row in self.rows:
                if self.x_key not in row:
                    raise ValueError(f"Missing x_key {self.x_key!r} in a row.")
                if self.group_key is not None:
                    group_value = row.get(self.group_key)
                    if isinstance(group_value, bool) or not isinstance(
                        group_value, (str, int, float)
                    ):
                        raise ValueError(
                            "group_key values must be strings or finite numbers."
                        )
                    pair = json.dumps(
                        [_group_identity(row[self.x_key]), _group_identity(group_value)]
                    )
                    if pair in seen_groups:
                        raise ValueError("Each x_key/group_key pair must be unique.")
                    seen_groups.add(pair)
                    group_values.add(_group_identity(group_value))
                    if len(group_values) > 8:
                        raise ValueError("Grouped bars support at most eight groups.")
                if self.chart_type == "scatter":
                    x_value = row[self.x_key]
                    if (
                        isinstance(x_value, bool)
                        or not isinstance(x_value, (int, float, str))
                        or (isinstance(x_value, str) and not _NUMBER.fullmatch(x_value))
                    ):
                        raise ValueError("Scatter x values must be finite numbers.")
                    try:
                        if not math.isfinite(float(x_value)):
                            raise ValueError("Scatter x values must be finite numbers.")
                    except (OverflowError, ValueError) as exc:
                        raise ValueError(
                            "Scatter x values must be finite numbers."
                        ) from exc
                for key in self.y_keys:
                    if key not in row:
                        raise ValueError(f"Missing y_key {key!r} in a row.")
                    value = row[key]
                    if value is None:
                        continue
                    if isinstance(value, bool) or not isinstance(
                        value, (int, float, str)
                    ):
                        raise ValueError(
                            f"Series {key!r} must contain finite numbers or null."
                        )
                    if isinstance(value, str) and not _NUMBER.fullmatch(value):
                        raise ValueError(
                            f"Series {key!r} must contain finite numbers or null."
                        )
                    try:
                        number = float(value)
                    except (OverflowError, ValueError) as exc:
                        raise ValueError(
                            f"Series {key!r} must contain finite numbers or null."
                        ) from exc
                    if not math.isfinite(number):
                        raise ValueError(
                            f"Series {key!r} must contain finite numbers or null."
                        )
                    if self.chart_type in _SINGLE_NONNEGATIVE and number < 0:
                        raise ValueError(
                            f"{self.chart_type} values must be nonnegative."
                        )
        payload = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
        )
        if len(payload) > 50_000:
            raise ValueError("Chart payload exceeds 50,000 serialized characters.")
        return self


class ChartPart(ChartRenderToolArgs):
    type: Literal["chart"] = "chart"


def render_chart(payload: dict[str, object]) -> ToolInvocationResult:
    """Validate rows before producing a typed chart and short tool summary."""
    args = ChartRenderToolArgs.model_validate(payload)
    part = ChartPart.model_validate(args.model_dump())
    return ToolInvocationResult(
        tool_ref=TOOL_REF_CHART_RENDER,
        blocks=(
            ToolContentBlock(
                kind=ToolContentKind.TEXT,
                text=f"{part.title.strip()}: rendered {len(part.rows)} row(s) as {part.chart_type}.",
            ),
        ),
        ui_parts=(cast(UiPart, part),),
    )
