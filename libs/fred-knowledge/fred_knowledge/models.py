# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Knowledge Flow's document models, admitted by the Control Plane.

The Control Plane decides which embedding and vision models an organization's
documents use and sends the approved connection, a reference without secret. This
workload accepts it only when its own configured credential binding attests the
same destination, then reads the key from its environment. Knowledge Flow keeps no
model choice of its own. Chat clients take the admitted protocol and options from the
shared `InferenceAdmission.chat_settings`; embeddings call the destination's
`/embeddings`. Like Ralph, Knowledge Flow supports the `standard` route with an API
key or no authentication, without an API version or gateway header; other admitted
forms are refused explicitly, before any remote call.
"""

from __future__ import annotations

import os
from threading import Lock

from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_embeddings, get_model
from fred_sdk.contracts.weaver import InferenceAdmission, InferenceCredentialBinding
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

# The OpenAI client requires a bearer; an unauthenticated destination ignores it.
_NO_AUTH_BEARER = "fred-no-inference-auth"


class DocumentModelError(RuntimeError):
    """An admitted document model this workload cannot or may not call."""


class DocumentModels:
    """Builds the admitted models once per approved offer and source revision."""

    def __init__(self, credentials: tuple[InferenceCredentialBinding, ...]) -> None:
        self._credentials = {item.credential_binding: item for item in credentials}
        if len(self._credentials) != len(credentials):
            raise ValueError("Duplicate inference credential binding")
        self._embeddings: dict[tuple, Embeddings] = {}
        self._chat: dict[tuple, BaseChatModel] = {}
        self._lock = Lock()

    def embeddings(self, admission: InferenceAdmission) -> Embeddings:
        key = self.identity(admission)
        with self._lock:
            if key not in self._embeddings:
                api_key = self._credential(admission)
                settings: dict = {"base_url": admission.connection.base_url(self._model(admission))}
                # Token-length checks assume OpenAI's tokenizer.
                if admission.connection.dialect != "openai":
                    settings["check_embedding_ctx_length"] = False
                config = ModelConfiguration(provider="openai", name=self._model(admission), settings=settings)
                self._embeddings[key] = get_embeddings(config, inference_api_key=api_key)
            return self._embeddings[key]

    def chat(self, admission: InferenceAdmission) -> BaseChatModel:
        """A chat model: image description, or a document tool's map-reduce."""
        key = self.identity(admission)
        with self._lock:
            if key not in self._chat:
                api_key = self._credential(admission)
                config = ModelConfiguration(provider="openai", name=self._model(admission), settings=admission.chat_settings())
                self._chat[key] = get_model(config, inference_api_key=api_key)
            return self._chat[key]

    @staticmethod
    def identity(admission: InferenceAdmission) -> tuple:
        """What a built client depends on: offer, source revision, connection and options.

        Caches holding a client, such as a corpus store, key on this identity so that
        a new admission is never served by a client built for a previous one."""
        selection = admission.selection
        return (selection.key.identity, selection.source_revision, admission.connection.model_dump_json(), selection.options.model_dump_json())

    @staticmethod
    def _model(admission: InferenceAdmission) -> str:
        return admission.selection.key.upstream_model_id

    def _credential(self, admission: InferenceAdmission) -> SecretStr:
        connection = admission.connection
        local = self._credentials.get(connection.credential_binding)
        if local is None or not local.attests(connection):
            raise DocumentModelError("The admitted model connection is not attested by this workload's credential bindings")
        if connection.route != "standard" or connection.api_version or connection.auth.kind == "entra" or connection.auth.gateway_key_header:
            raise DocumentModelError("Knowledge Flow supports the standard route with an API key or no authentication")
        secret = os.environ.get(local.api_key_env) if local.api_key_env else _NO_AUTH_BEARER
        if not secret:
            raise DocumentModelError("The admitted model's credential is unavailable")
        return SecretStr(secret)
