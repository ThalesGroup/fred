# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Shared contract for work prepared outside the agent turn."""

import json
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class PreparationSpec(BaseModel):
    """Manifest declaration for one capability's durable preparation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_slots: tuple[str, ...] = ()
    min_assets: int = Field(default=0, ge=0, le=32)
    activation_field: str | None = Field(default=None, min_length=1, max_length=128)
    config_fields: tuple[str, ...] | None = None
    public_config_fields: tuple[str, ...] = ()
    rules_version: str = Field(min_length=1, max_length=64)
    gates_readiness: bool = True
    max_input_bytes: int = Field(default=64 * 1024 * 1024, ge=1, le=64 * 1024 * 1024)
    max_attempts: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=1200, ge=1, le=7200)

    @model_validator(mode="after")
    def _unique_slots(self) -> "PreparationSpec":
        if any(not key for key in self.asset_slots) or len(
            set(self.asset_slots)
        ) != len(self.asset_slots):
            raise ValueError("Preparation asset slots must be nonempty and unique")
        if self.min_assets and not self.asset_slots:
            raise ValueError("Preparation assets require a declared slot")
        if self.config_fields is not None and (
            any(not key or len(key) > 128 for key in self.config_fields)
            or len(set(self.config_fields)) != len(self.config_fields)
        ):
            raise ValueError("Preparation config fields must be nonempty and unique")
        if (
            any(not key or len(key) > 128 for key in self.public_config_fields)
            or len(set(self.public_config_fields)) != len(self.public_config_fields)
            or (
                self.config_fields is not None
                and not set(self.public_config_fields) <= set(self.config_fields)
            )
        ):
            raise ValueError("Public preparation fields must be unique input fields")
        return self


class PreparationAsset(BaseModel):
    """One immutable input reference, resolved by the preparation worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    slot_key: str = Field(min_length=1, max_length=128)
    filename: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0, le=64 * 1024 * 1024)


class PreparationWork(BaseModel):
    """Canonical control-plane work record; Temporal receives only its id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    preparation_id: UUID
    owner_kind: Literal["agent", "platform"]
    owner_id: str = Field(min_length=1, max_length=255)
    runtime_id: str = Field(min_length=1, max_length=255)
    capability_id: str = Field(min_length=1, max_length=255)
    input_revision: str = Field(min_length=1, max_length=128)
    rules_version: str = Field(min_length=1, max_length=64)
    attempt: int = Field(default=0, ge=0, le=10)
    max_attempts: int = Field(default=3, ge=1, le=10)
    assets: tuple[PreparationAsset, ...] = Field(default=(), max_length=32)
    config: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _bounded_payload(self) -> "PreparationWork":
        if len(json.dumps(self.config).encode("utf-8")) > 128 * 1024:
            raise ValueError("Preparation config exceeds 128 KiB")
        if len({asset.asset_id for asset in self.assets}) != len(self.assets):
            raise ValueError("Preparation assets must have distinct ids")
        if sum(asset.size for asset in self.assets) > 64 * 1024 * 1024:
            raise ValueError("Preparation assets exceed 64 MiB")
        return self


class PreparationResult(BaseModel):
    """Opaque derived artifact reference published after revision fencing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str = Field(min_length=1, max_length=512)
    summary: str | None = Field(default=None, max_length=2000)


class PreparationAssetReader(Protocol):
    async def read(self, asset_id: UUID) -> bytes:
        pass


class PreparationArtifactStore(Protocol):
    async def write(self, path: str, content: bytes) -> None:
        pass

    async def read(self, path: str) -> bytes:
        pass

    async def delete(self, path: str) -> None:
        pass


class PreparationVisionPort(Protocol):
    async def describe(self, image: bytes, prompt: str) -> str:
        pass

    async def available(self) -> bool:
        pass


@dataclass(frozen=True)
class PreparationContext:
    work: PreparationWork
    assets: PreparationAssetReader
    artifacts: PreparationArtifactStore
    vision: PreparationVisionPort | None = None
