# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Typed consumer of the Control Plane space runtime resolver (M3/M4).

These are non-secret facts, never a persisted or caller-supplied execution grant.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .managed_mcp import McpBinding
from .skills import SkillCatalog


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


_API_ROOT = re.compile(
    r"(?P<scheme>https?)://(?P<host>[a-z0-9._~-]+)(?::(?P<port>[1-9][0-9]{0,4}))?"
    r"(?P<path>(?:/[A-Za-z0-9._~:-]+)*)"
)
_NUMERIC_HOST = re.compile(r"(?:.*\.)?(?:[0-9]+|0x[0-9a-f]*)\.?")
_RESERVED_HEADERS = {"authorization", "host", "cookie", "transfer-encoding"}


def _bounded(value: str, max_bytes: int) -> bool:
    return (
        bool(value)
        and len(value.encode()) <= max_bytes
        and value.strip() == value
        and not any(unicodedata.category(char) == "Cc" for char in value)
    )


def canonical_api_root(value: str) -> bool:
    """Runtimes compare this root byte for byte, so nothing may need normalizing.

    An IPv6 literal is refused: use a DNS name. Pinned by `inference_connections.json`.
    """
    match = _API_ROOT.fullmatch(value)
    if match is None or len(value) > 2048:
        return False
    port = int(match["port"] or 0)
    if port > 65535 or port == {"http": 80, "https": 443}[match["scheme"]]:
        return False
    if any(part in {".", ".."} for part in match["path"].split("/")):
        return False
    if _NUMERIC_HOST.fullmatch(match["host"]):
        try:
            ipaddress.IPv4Address(match["host"])
        except ValueError:
            return False
    return True


class ModelAuth(ResolverFact):
    """Authentication facts only: the secrets stay in the pod's local binding."""

    kind: Literal["none", "api_key", "entra"]
    tenant_id: str | None = None
    client_id: str | None = None
    scope: str | None = None
    gateway_key_header: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,128}$"
    )


class ModelConnection(ResolverFact):
    """One destination, independent of the vendor. Mirror of the Rust contract."""

    credential_binding: str
    api_root: str
    wire: Literal["openai_chat", "openai_responses"]
    route: Literal["standard", "azure_deployment"]
    api_version: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$")
    dialect: Literal["openai", "openai_compatible", "mistral"]
    auth: ModelAuth

    @model_validator(mode="after")
    def valid_connection(self) -> Self:
        auth = self.auth
        entra = auth.kind == "entra"
        header = (auth.gateway_key_header or "").lower()
        if (
            not _bounded(self.credential_binding, 128)
            or not canonical_api_root(self.api_root)
            or (entra and not self.api_root.startswith("https://"))
            or (
                self.route == "azure_deployment"
                and (self.wire != "openai_chat" or self.api_version is None)
            )
            or header in _RESERVED_HEADERS
            or header.startswith("content-")
            or any(
                (fact is None) == entra
                or (fact is not None and not _bounded(fact, limit))
                for fact, limit in (
                    (auth.tenant_id, 128),
                    (auth.client_id, 128),
                    (auth.scope, 256),
                )
            )
        ):
            raise ValueError("Invalid inference connection")
        return self

    def base_url(self, model: str) -> str:
        if self.route == "azure_deployment":
            return f"{self.api_root}/deployments/{model}"
        return self.api_root

    def request_url(self, model: str) -> str:
        """The only generation URL this connection may reach for one model.

        `wire` selects the generation protocol only. An embedding offer is always
        called at `{base_url}/embeddings`, the one embedding endpoint of these APIs."""
        leaf = "responses" if self.wire == "openai_responses" else "chat/completions"
        query = f"?api-version={self.api_version}" if self.api_version else ""
        return f"{self.base_url(model)}/{leaf}{query}"


_ENV_NAME = r"^[A-Za-z_][A-Za-z0-9_]*$"


class InferenceCredentialBinding(BaseModel):
    """A workload's local attestation of one admitted destination, read from its own
    configuration: variable names only, never secrets. Every model client (Agent Pod,
    Knowledge Flow) checks the Control Plane's admitted connection against it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    credential_binding: str = Field(min_length=1, max_length=128)
    api_root: str
    api_key_env: str | None = Field(default=None, pattern=_ENV_NAME)
    client_secret_env: str | None = Field(default=None, pattern=_ENV_NAME)
    gateway_key_env: str | None = Field(default=None, pattern=_ENV_NAME)

    @model_validator(mode="after")
    def approved_root(self) -> Self:
        if not canonical_api_root(self.api_root):
            raise ValueError("Inference API root must be a canonical HTTP(S) URL")
        return self

    def attests(self, connection: ModelConnection) -> bool:
        """Same binding and destination, and local secrets for exactly its authentication."""
        auth = connection.auth
        return (
            self.credential_binding == connection.credential_binding
            and self.api_root == connection.api_root
            and (self.api_key_env is not None) == (auth.kind == "api_key")
            and (self.client_secret_env is not None) == (auth.kind == "entra")
            and (self.gateway_key_env is not None)
            == (auth.gateway_key_header is not None)
        )


class EffectiveModelOptions(ModelOptions):
    reasoning_effort: Literal["high"] | None = None


class InferenceSelection(ResolverFact):
    key: ModelOfferKey
    source: Literal[
        "default", "user_choice", "instance_recommendation", "withdrawal_fallback"
    ]
    options: EffectiveModelOptions
    source_revision: int = Field(gt=0, strict=True)
    snapshot_revision: int = Field(gt=0, strict=True)
    policy_revision: int = Field(gt=0, strict=True)


class InferenceAdmission(ResolverFact):
    selection: InferenceSelection
    connection: ModelConnection
    encrypted_credential: str | None = Field(default=None, repr=False)
    corpus_generation: UUID | None = None

    def chat_settings(self) -> dict[str, Any]:
        """OpenAI-compatible chat client settings making exactly the admitted call.

        Protocol, destination and options come from the admission alone: an unset option
        stays unset rather than taking a client default. Authentication is the caller's,
        from its local credential binding."""
        connection = self.connection
        model = self.selection.key.upstream_model_id
        options: dict[str, Any] = self.selection.options.model_dump(exclude_none=True)
        options.setdefault("temperature", None)
        # Through the body: ChatOpenAI renames this option to max_completion_tokens,
        # which these servers would ignore.
        if (
            connection.wire == "openai_chat"
            and connection.dialect == "openai_compatible"
            and "max_tokens" in options
        ):
            options["extra_body"] = {"max_tokens": options.pop("max_tokens")}
        version = connection.api_version
        return {
            "base_url": connection.base_url(model),
            # Explicit: LangChain would otherwise choose from the model and payload.
            "use_responses_api": connection.wire == "openai_responses",
            "default_query": {"api-version": version} if version else None,
            **options,
        }


class ModelMetadata(ResolverFact):
    chat: bool | None
    chat_provenance: Literal["source_guarantee", "api_metadata"] | None
    reasoning: bool | None = None
    embedding: bool | None = None
    audio_transcription: bool | None = None
    vision: bool | None = None
    display_name: str | None
    context_window_tokens: int | None
    max_input_tokens: int | None
    max_output_tokens: int | None
    reasoning_required: bool | None = None
    reasoning_efforts: tuple[str, ...] | None = None
    reasoning_default: str | None = None
    reasoning_transport: str | None = None
    reasoning_replay: str | None = None
    tool_calling: bool | None = None
    structured_output: bool | None = None
    provider_capabilities: dict[str, bool] = Field(default_factory=dict)
    provenance: dict[str, str] = Field(default_factory=dict)


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
    default: ModelOfferKey | None
    fallback: ModelOfferKey | None
    title: ModelOfferKey | None = None
    creation_assistant: ModelOfferKey | None = None
    embedding: ModelOfferKey | None = None
    embedding_locked: bool = False
    vision: ModelOfferKey | None = None
    transcription: ModelOfferKey | None = None
    created_by: str | None
    created_at: datetime | None
    updated_by: str | None
    updated_at: datetime | None


class ModelUseOptions(ResolverFact):
    unverified: bool
    chat: bool
    embedding: bool
    vision: bool
    transcription: bool


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
    uses: ModelUseOptions | None = None
    observation: ModelObservation | None


class RuntimeModels(ResolverFact):
    policy: OrganizationModelPolicy
    # Effective space default is a fact, never an alternative to admitted inference.
    default: ModelOfferKey | None
    recommendation: ModelOfferKey | None
    options: ModelOptions
    offers: tuple[RuntimeModelOffer, ...]
    reasoning_default_on: tuple[ModelOfferKey, ...]

    @model_validator(mode="after")
    def coherent(self) -> RuntimeModels:
        keys = {offer.key.identity for offer in self.offers}
        permitted = {key.identity for key in self.policy.permitted}
        expected = permitted.copy()
        expected.update(
            k.identity
            for k in (
                self.recommendation,
                self.default,
                self.policy.default,
                self.policy.fallback,
                self.policy.embedding,
                self.policy.vision,
                self.policy.transcription,
            )
            if k
        )
        expected.update(key.identity for key in self.reasoning_default_on)
        if len(keys) != len(self.offers) or not expected.issubset(keys):
            raise ValueError("Incomplete or duplicate model facts")
        for offer in self.offers:
            if offer.permitted and offer.key.identity not in permitted:
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
                    or metadata.chat is False
                    or not (offer.uses.chat if offer.uses else metadata.chat is True)
                    or any(d != "discovery_unavailable" for d in offer.diagnostics)
                ):
                    raise ValueError("Inconsistent model candidate")
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


class RuntimeAttachment(ResolverFact):
    document_id: UUID
    name: str
    mime: str


class TitleAdmission(ResolverFact):
    attempt_id: UUID
    inference: InferenceAdmission


class WeaverRuntimeResolution(ResolverFact):
    subject_id: str
    run_id: str | None
    conversation_id: str | None
    space: RuntimeSpace
    agent: RuntimeAgent
    models: RuntimeModels
    # Organization text admitted with the canonical space; None uses the runtime default.
    platform_prompt: str | None
    mcp_bindings: tuple[McpBinding, ...] = ()
    skills: SkillCatalog | None = None
    skill_files: dict[str, str] | None = None
    title: TitleAdmission | None = None
    attachments: tuple[RuntimeAttachment, ...]
    authorized_space_ids: tuple[UUID, ...]

    @model_validator(mode="after")
    def owning_organization(self) -> Self:
        if len(set(self.authorized_space_ids)) != len(self.authorized_space_ids):
            raise ValueError("Duplicate authorized spaces")
        if self.title and not self.conversation_id:
            raise ValueError("Title requires a conversation")
        if self.attachments and not self.conversation_id:
            raise ValueError("Attachments require a conversation")
        if self.attachments:
            UUID(self.conversation_id or "")
        ids = [attachment.document_id for attachment in self.attachments]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate attachment facts")
        if self.space.organization_id != self.models.policy.organization_id:
            raise ValueError("Model policy belongs to another organization")
        return self


class WeaverRuntimeBinding(WeaverRuntimeResolution):
    """Actual execution requires the private inference admission."""

    inference: InferenceAdmission
