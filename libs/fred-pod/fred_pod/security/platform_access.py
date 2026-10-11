# SPDX-License-Identifier: Apache-2.0
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimPath = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=256)]],
    Field(min_length=1, max_length=16),
]


class PlatformAccessCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: ClaimPath
    operator: Literal["equals", "not_equals", "contains", "not_contains", "regex"]
    value: str = Field(min_length=1, max_length=2048)
    case_sensitive: bool = False

    @model_validator(mode="after")
    def validate_condition(self):
        if not all(key.strip() for key in self.claim):
            raise ValueError("Claim keys must not be blank")
        if self.operator == "regex":
            try:
                re.compile(self.value)
            except re.error:
                raise ValueError("Invalid regular expression") from None
        elif len(self.value) > 1024:
            raise ValueError("Literal operands must not exceed 1024 characters")
        return self


class PlatformAccessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["allow", "block"] = "allow"
    combination: Literal["all", "any"] = "all"
    conditions: list[PlatformAccessCondition] = Field(min_length=1, max_length=16)
