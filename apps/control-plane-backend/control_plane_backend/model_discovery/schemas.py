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

from datetime import datetime

from fred_sdk.contracts.context import ModelBinding
from pydantic import BaseModel, Field


class DiscoveredModel(BaseModel):
    id: str
    name: str
    provider: str
    display_name: str | None = None
    profile_ids: list[str] = Field(default_factory=list)
    chat_profile_ids: list[str] = Field(default_factory=list)
    context_window_tokens: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None


class DiscoverySourceStatus(BaseModel):
    source_id: str
    yaml_url: str
    override_url: str | None = None
    effective_url: str
    available_models: list[DiscoveredModel] = Field(default_factory=list)
    removed_models: list[DiscoveredModel] = Field(default_factory=list)
    new_ids: list[str] = Field(default_factory=list)
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_error: str | None = None


class UnverifiedRuntime(BaseModel):
    runtime_id: str
    base_url: str


class ModelDiscoveryStatus(BaseModel):
    sources: list[DiscoverySourceStatus] = Field(default_factory=list)
    refresh_error: str | None = None
    unverified_runtimes: list[UnverifiedRuntime] = Field(default_factory=list)
    verified_source_ids: list[str] = Field(default_factory=list)


class SetDiscoveryUrlRequest(BaseModel):
    url: str | None = None


class PlatformModelFallback(BaseModel):
    binding: ModelBinding | None = None
    profile_id: str | None = None


class SetPlatformModelFallbackRequest(BaseModel):
    profile_id: str = Field(min_length=1)
