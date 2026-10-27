# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Existing chat factory, consuming only the active Weaver turn's facts."""

from __future__ import annotations

import json
import logging
import os
from typing import Protocol

from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_embeddings, get_model
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import AgentDefinition
from fred_sdk.contracts.runtime import ChatModelFactoryPort
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from fred_runtime.app.config import InferenceCredentialBinding
from fred_runtime.support.reasoning_replay import with_mistral_reasoning_replay

from .contracts import ModelCapability, ModelRoutingError, ModelSelection
from .guard import checked_clients, guarded_model
from .resolver import ModelRoutingResolver
from .turn import current_turn

logger = logging.getLogger(__name__)


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
        self._credentials = {item.source_id: item for item in credentials}
        if len(self._credentials) != len(credentials):
            raise ModelRoutingError("Duplicate inference source provisioning")

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
        offer, source = ModelRoutingResolver(authority.binding.models).resolve(
            authority.choice
        )
        connection = offer.connection
        if connection is None:
            raise ModelRoutingError("Trusted inference connection is missing")
        if connection.provider != "openai":
            raise ModelRoutingError(
                "Inference adapter is not connected; only OpenAI-compatible sources are supported"
            )
        local = self._credentials.get(offer.key.source_id)
        if (
            local is None
            or local.api_root != connection.api_root
            or local.credential_binding != connection.credential_binding
        ):
            raise ModelRoutingError(
                "Inference source provisioning does not match the approved connection"
            )
        # Explicit options only; do not inject core's default temperature.
        options = authority.binding.models.options.model_dump(exclude_none=True)
        options.setdefault("temperature", None)
        effort = authority.reasoning_effort(offer)
        if effort is not None:
            options["reasoning_effort"] = effort
        config = ModelConfiguration(
            provider="openai",
            name=offer.key.upstream_model_id,
            settings={"base_url": connection.api_root, **options},
        )
        identity = json.dumps(
            offer.key.identity, ensure_ascii=False, separators=(",", ":")
        )
        selection = ModelSelection(
            source=source,
            capability=ModelCapability.CHAT,
            profile_id=identity,
            capability_id=identity,
            model=config,
        )
        model = authority.models.get(offer.key)
        if model is None:
            secret = os.environ.get(local.api_key_env)
            if not secret:
                raise ModelRoutingError(
                    "Inference credential is unavailable for the approved source"
                )
            built = get_model(
                config,
                inference_api_key=SecretStr(secret),
                wrap_clients=checked_clients(authority, offer, secret),
            )
            if type(built) is not ChatOpenAI:
                raise TypeError("Expected the connected OpenAI-compatible client")
            model = guarded_model(with_mistral_reasoning_replay(built), authority.check)
            authority.models[offer.key] = model
        logger.info(
            "[MODEL_ROUTING] source=%s requested=%s actual=%s policy_revision=%s",
            source.value,
            authority.choice
            or authority.binding.models.recommendation
            or authority.binding.models.policy.default,
            offer.key,
            authority.binding.models.policy.revision,
        )
        return model, selection
