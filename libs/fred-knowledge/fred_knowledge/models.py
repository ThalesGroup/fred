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

import json
import math
import os
from threading import Lock

import httpx
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
        self._rerank_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=3.0, pool=3.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            follow_redirects=False,
        )

    async def close(self) -> None:
        await self._rerank_client.aclose()

    async def rerank(self, admission: InferenceAdmission, query: str, documents: list[str], top_n: int) -> list[int]:
        """Call an admitted indexed-results rerank endpoint and return ranked input indices."""
        if admission.connection.wire != "rerank" or not 0 < top_n <= len(documents) <= 100:
            raise DocumentModelError("Invalid rerank admission or candidate count")
        credential = self._credential(admission).get_secret_value()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if admission.connection.auth.kind == "api_key":
            headers["Authorization"] = f"Bearer {credential}"
        try:
            request = self._rerank_client.build_request(
                "POST",
                admission.connection.request_url(self._model(admission)),
                headers=headers,
                json={"model": self._model(admission), "query": query, "documents": documents, "top_n": top_n},
            )
            response = await self._rerank_client.send(request, stream=True)
            try:
                response.raise_for_status()
                if response.headers.get("content-length") and int(response.headers["content-length"]) > 1024 * 1024:
                    raise DocumentModelError("Rerank response exceeds size limit")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > 1024 * 1024:
                        raise DocumentModelError("Rerank response exceeds size limit")
                results = json.loads(body)["results"]
            finally:
                await response.aclose()
            if not isinstance(results, list) or len(results) != top_n:
                raise DocumentModelError("Invalid rerank response")
            indices: set[int] = set()
            ranked: list[tuple[int, float]] = []
            for item in results:
                index, score = item["index"], item["relevance_score"]
                if type(index) is not int or index < 0 or index >= len(documents) or index in indices:
                    raise DocumentModelError("Invalid rerank response")
                if type(score) not in (int, float) or not math.isfinite(score):
                    raise DocumentModelError("Invalid rerank response")
                indices.add(index)
                ranked.append((index, score))
            return [index for index, _ in sorted(ranked, key=lambda entry: entry[1], reverse=True)]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise DocumentModelError("Rerank service unavailable or returned an invalid response") from error

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
