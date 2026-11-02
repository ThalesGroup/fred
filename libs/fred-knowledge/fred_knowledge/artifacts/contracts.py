# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Artifact(Contract):
    path: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
