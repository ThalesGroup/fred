# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from typing import Literal, Optional

from pydantic import BaseModel, Field

DTypes = Literal["string", "integer", "float", "boolean", "datetime", "unknown"]


class TabularColumnSchema(BaseModel):
    name: str
    dtype: DTypes
    is_categorical: Optional[bool] = Field(
        default=None,
        description=(
            "For string columns, whether the count of distinct non-null values is "
            "between 1 and max_categories(row_count), with null rows included in "
            "row_count. None for non-string or older columns without this analysis."
        ),
    )
    has_two_values: Optional[bool] = Field(
        default=None,
        description=("For string columns, whether exactly two distinct non-null values were observed. This does not assign true/false meaning to those values."),
    )
    sample_values: Optional[list[str]] = Field(
        default=None,
        description=("Every distinct non-null string value when is_categorical is true, preserving exact casing for SQL filters. None otherwise."),
    )
    min_value: int | float | None = Field(
        default=None,
        description="Smallest finite non-null value of an integer or float column. None when unavailable.",
    )
    max_value: int | float | None = Field(
        default=None,
        description="Largest finite non-null value of an integer or float column. None when unavailable.",
    )
