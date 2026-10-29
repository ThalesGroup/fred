# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Typed consumer of the Control Plane space runtime resolver (M3/M4).

These are non-secret facts, never a persisted or caller-supplied execution grant.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResolverFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ModelOfferKey(ResolverFact):
    source_id: str = Field(min_length=1)
    upstream_model_id: str = Field(min_length=1)

    @property
    def identity(self) -> tuple[str, str]:
        return self.source_id, self.upstream_model_id


class ModelOptions(ResolverFact):
    temperature: float | None = Field(default=None, allow_inf_nan=False)
    max_tokens: int | None = Field(default=None, gt=0, strict=True)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class ModelConnection(ResolverFact):
    provider: str
    api_root: str
    credential_binding: str


class ModelMetadata(ResolverFact):
    chat: bool | None
    chat_provenance: Literal["source_guarantee", "api_metadata"] | None
    reasoning: bool | None = None
    display_name: str | None
    context_window_tokens: int | None
    max_input_tokens: int | None
    max_output_tokens: int | None


class ModelObservation(ResolverFact):
    source_id: str
    source_revision: int
    enabled: bool
    state: str
    error_code: str | None
    checked_at: datetime | None
    last_success_at: datetime | None
    snapshot_revision: int
    snapshot_source_revision: int | None


class OrganizationModelPolicy(ResolverFact):
    organization_id: UUID
    revision: int
    permitted: tuple[ModelOfferKey, ...]
    reasoning_enabled: tuple[ModelOfferKey, ...]
    default: ModelOfferKey | None
    fallback: ModelOfferKey | None
    created_by: str | None
    created_at: datetime | None
    updated_by: str | None
    updated_at: datetime | None


class RuntimeModelOffer(ResolverFact):
    key: ModelOfferKey
    permitted: bool
    candidate: bool
    selectable: bool
    diagnostics: tuple[
        Literal[
            "unknown_offer",
            "not_permitted",
            "source_disabled",
            "source_revision_unobserved",
            "discovery_unavailable",
            "withdrawn",
            "chat_not_established",
            "options_exceed_known_limit",
        ],
        ...,
    ]
    metadata: ModelMetadata | None
    observation: ModelObservation | None
    connection: ModelConnection | None = None


class RuntimeModels(ResolverFact):
    policy: OrganizationModelPolicy
    recommendation: ModelOfferKey | None
    options: ModelOptions
    legacy_profile_id: str | None
    requires_reselection: bool
    offers: tuple[RuntimeModelOffer, ...]

    @model_validator(mode="after")
    def coherent(self) -> RuntimeModels:
        keys = [o.key for o in self.offers]
        expected = set(self.policy.permitted)
        expected.update(
            k
            for k in (self.recommendation, self.policy.default, self.policy.fallback)
            if k
        )
        if len(set(keys)) != len(keys) or set(keys) != expected:
            raise ValueError("Incomplete or duplicate model facts")
        reasoning = self.policy.reasoning_enabled
        if len(set(reasoning)) != len(reasoning) or not set(reasoning).issubset(
            self.policy.permitted
        ):
            raise ValueError("Reasoning outside permitted model set")
        for offer in self.offers:
            if offer.permitted != (offer.key in self.policy.permitted):
                raise ValueError("Inconsistent model permission")
            if offer.candidate:
                obs, metadata = offer.observation, offer.metadata
                if (
                    not offer.permitted
                    or obs is None
                    or not obs.enabled
                    or obs.source_id != offer.key.source_id
                    or obs.snapshot_source_revision != obs.source_revision
                    or metadata is None
                    or metadata.chat is not True
                    or any(d != "discovery_unavailable" for d in offer.diagnostics)
                ):
                    raise ValueError("Inconsistent model candidate")
            if offer.connection is not None and not offer.candidate:
                raise ValueError("Connection outside candidate set")
        return self


class RuntimeSpace(ResolverFact):
    id: UUID
    kind: Literal["personal", "team", "project", "organization"]
    organization_id: UUID
    team_id: UUID | None
    project_id: UUID | None


class RuntimeAgent(ResolverFact):
    instance_id: UUID
    runtime_id: str
    template_id: UUID
    template_key: str
    configuration_revision: int = Field(gt=0, strict=True)
    configuration_updated_at: datetime
    configuration: dict[str, Any]


class WeaverRuntimeBinding(ResolverFact):
    subject_id: str
    run_id: str | None
    conversation_id: str | None
    space: RuntimeSpace
    agent: RuntimeAgent
    models: RuntimeModels

    @model_validator(mode="after")
    def owning_organization(self) -> WeaverRuntimeBinding:
        if self.space.organization_id != self.models.policy.organization_id:
            raise ValueError("Model policy belongs to another organization")
        return self
