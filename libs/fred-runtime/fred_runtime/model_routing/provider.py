# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Existing chat factory, consuming only the active Weaver turn's facts."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Collection
from typing import TYPE_CHECKING, Protocol

from azure.identity import AzureAuthorityHosts, ClientSecretCredential
from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_embeddings, get_model
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import AgentDefinition
from fred_sdk.contracts.runtime import ChatModelFactoryPort
from fred_sdk.contracts.weaver import InferenceAdmission, ModelAuth
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from fred_runtime.support.reasoning_replay import with_mistral_reasoning_replay

from .contracts import (
    ModelCapability,
    ModelRoutingError,
    ModelSelection,
    ModelSelectionSource,
)
from .guard import NO_AUTH_BEARER, checked_clients, guarded_model
from .turn import TurnAuthority, current_turn

if TYPE_CHECKING:
    from fred_runtime.app.config import InferenceCredentialBinding

logger = logging.getLogger(__name__)

_SEGMENT = re.compile(r"(?!\.{1,2}$)[A-Za-z0-9._-]+")
_ENTRA_UNAVAILABLE = "Inference authentication is unavailable for the approved source"
_TEMPERATURE_REFUSED = "The model client does not accept the admitted temperature"


def _local_secret(variable: str | None) -> str:
    secret = os.environ.get(variable) if variable else None
    if not secret:
        raise ModelRoutingError(
            "Inference credential is unavailable for the approved source"
        )
    return secret


class ModelProvider(Protocol):
    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> object: ...


class FredCoreModelProvider:
    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> object:
        return (
            get_embeddings(model_config)
            if capability == ModelCapability.EMBEDDING
            else get_model(model_config)
        )


class RoutedChatModelFactory(ChatModelFactoryPort):
    def __init__(
        self, *, credentials: tuple[InferenceCredentialBinding, ...] = ()
    ) -> None:
        self._credentials = {item.credential_binding: item for item in credentials}
        if len(self._credentials) != len(credentials):
            raise ModelRoutingError("Duplicate inference credential binding")
        self._entra: dict[tuple[str, str, str], ClientSecretCredential] = {}

    def build(
        self, definition: AgentDefinition, binding: BoundRuntimeContext
    ) -> BaseChatModel:
        return self.build_for_chat(definition=definition, binding=binding)[0]

    def build_for_chat(
        self, *, definition: AgentDefinition, binding: BoundRuntimeContext
    ) -> tuple[BaseChatModel, ModelSelection]:
        authority = current_turn()
        authority.check_context(binding.runtime_context, definition.agent_id)
        if binding.runtime_context.chat_profile_id is not None:
            raise ModelRoutingError(
                "Legacy model profile requires explicit offer re-selection"
            )
        return self._build_admitted(authority, authority.binding.inference)

    def build_for_title(self) -> BaseChatModel:
        authority = current_turn()
        title = authority.binding.title
        if title is None:
            raise ModelRoutingError("No title inference was admitted")
        return self._build_admitted(authority, title.inference)[0]

    def _build_admitted(
        self, authority: TurnAuthority, admission: InferenceAdmission
    ) -> tuple[BaseChatModel, ModelSelection]:
        selection = admission.selection
        connection = admission.connection
        model_id = selection.key.upstream_model_id
        auth = connection.auth
        local = self._credentials.get(connection.credential_binding)
        if (
            local is None
            or local.api_root != connection.api_root
            or (local.api_key_env is not None) != (auth.kind == "api_key")
            or (local.client_secret_env is not None) != (auth.kind == "entra")
            or (local.gateway_key_env is not None)
            != (auth.gateway_key_header is not None)
        ):
            raise ModelRoutingError(
                "Inference source provisioning does not match the approved connection"
            )
        # This identifier becomes a path segment on this route.
        if connection.route == "azure_deployment" and not _SEGMENT.fullmatch(model_id):
            raise ModelRoutingError("Invalid model identifier for a deployment route")
        version = connection.api_version
        # Explicit options only; do not inject core's default temperature.
        options = selection.options.model_dump(exclude_none=True)
        options.setdefault("temperature", None)
        # Through the body: ChatOpenAI renames this option to max_completion_tokens,
        # which these servers would ignore.
        if (
            connection.wire == "openai_chat"
            and connection.dialect == "openai_compatible"
            and "max_tokens" in options
        ):
            options["extra_body"] = {"max_tokens": options.pop("max_tokens")}
        config = ModelConfiguration(
            provider="openai",
            name=model_id,
            settings={
                "base_url": connection.base_url(model_id),
                # Explicit: LangChain would otherwise choose from the model and payload.
                "use_responses_api": connection.wire == "openai_responses",
                "default_query": {"api-version": version} if version else None,
                **options,
            },
        )
        identity = json.dumps(
            selection.key.identity, ensure_ascii=False, separators=(",", ":")
        )
        provenance = ModelSelection(
            source=ModelSelectionSource(selection.source),
            capability=ModelCapability.CHAT,
            profile_id=identity,
            capability_id=identity,
            model=config,
        )
        model = authority.models.get(selection)
        if model is None:
            gateway = (
                (auth.gateway_key_header, _local_secret(local.gateway_key_env))
                if auth.gateway_key_header
                else None
            )
            api_key, bearers = self._authentication(local, auth)
            built = get_model(
                config,
                inference_api_key=api_key,
                wrap_clients=checked_clients(authority, admission, bearers, gateway),
            )
            if type(built) is not ChatOpenAI:
                raise TypeError("Expected the connected OpenAI-compatible client")
            # LangChain silently drops a temperature some models refuse, at construction
            # or when serializing. Every call path sends this payload. An admitted setting
            # is never ignored, and the guard would report this as lost authority.
            temperature = selection.options.temperature
            if (
                temperature is not None
                and built._get_request_payload([]).get("temperature") != temperature
            ):
                raise ModelRoutingError(_TEMPERATURE_REFUSED)
            if connection.dialect == "mistral":
                built = with_mistral_reasoning_replay(built)
            model = guarded_model(built, authority.check)
            authority.models[selection] = model
        logger.info(
            "Inference source=%s requested=%s model=%s policy_revision=%s source_revision=%s snapshot_revision=%s",
            selection.source,
            authority.choice,
            selection.key,
            selection.policy_revision,
            selection.source_revision,
            selection.snapshot_revision,
        )
        return model, provenance

    def _authentication(
        self, local: InferenceCredentialBinding, auth: ModelAuth
    ) -> tuple[SecretStr | Callable[[], str], Collection[str]]:
        """What the client sends, and the bearers the guard accepts for this model."""
        if auth.kind == "none":
            return SecretStr(NO_AUTH_BEARER), {NO_AUTH_BEARER}
        if auth.kind == "api_key":
            secret = _local_secret(local.api_key_env)
            return SecretStr(secret), {secret}
        credential = self._entra_credential(local, auth)
        issued: set[str] = set()

        def token() -> str:
            # Outside the except block: the Entra error must not stay as __context__.
            try:
                value = credential.get_token(str(auth.scope)).token
            except Exception:
                value = None
            if not value:
                raise ModelRoutingError(_ENTRA_UNAVAILABLE) from None
            issued.add(value)
            return value

        return token, issued

    def _entra_credential(
        self, local: InferenceCredentialBinding, auth: ModelAuth
    ) -> ClientSecretCredential:
        tenant_id, client_id = str(auth.tenant_id), str(auth.client_id)
        key = (local.credential_binding, tenant_id, client_id)
        credential = self._entra.get(key)
        if credential is not None:
            return credential
        secret = _local_secret(local.client_secret_env)
        try:
            # Explicit authority: AZURE_AUTHORITY_HOST must not redirect the client secret.
            # No retry, so that the two timeouts really bound the token request.
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=secret,
                authority=AzureAuthorityHosts.AZURE_PUBLIC_CLOUD,
                connection_timeout=5,
                read_timeout=15,
                retry_total=0,
            )
        except Exception:
            credential = None
        if credential is None:
            raise ModelRoutingError(_ENTRA_UNAVAILABLE) from None
        self._entra[key] = credential
        return credential
