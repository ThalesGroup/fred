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

from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
    UiPart,
)

ChartType = Literal["bar", "line", "area", "pie", "table"]
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")


class ChartRenderToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_type: ChartType
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
        for row in self.rows:
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
            if self.chart_type == "pie" and len(self.y_keys) != 1:
                raise ValueError("Pie charts require exactly one y_key.")
            for row in self.rows:
                if self.x_key not in row:
                    raise ValueError(f"Missing x_key {self.x_key!r} in a row.")
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
                    if self.chart_type == "pie" and number < 0:
                        raise ValueError("Pie values must be nonnegative.")
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
        tool_ref="chart.render",
        blocks=(
            ToolContentBlock(
                kind=ToolContentKind.TEXT,
                text=f"{part.title.strip()}: rendered {len(part.rows)} row(s) as {part.chart_type}.",
            ),
        ),
        ui_parts=(cast(UiPart, part),),
    )
