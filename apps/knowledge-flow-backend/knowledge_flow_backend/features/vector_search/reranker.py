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

"""Bounded local and remote document reranking for Knowledge Flow searches."""

import asyncio
import json
import math
from collections.abc import Callable, Sequence
from threading import Lock
from typing import Any

import httpx

from knowledge_flow_backend.common.model_api_keys import api_key_for_role
from knowledge_flow_backend.common.structures import RerankerModelConfiguration

MAX_RERANK_CANDIDATES = 100
MAX_RERANK_TEXT_CHARS = 8192
MAX_RERANK_BODY_BYTES = 1024 * 1024
MAX_REMOTE_TEXT_BYTES = 8192
REMOTE_TOTAL_TIMEOUT_SECONDS = 15.0
LOCAL_QUEUE_TIMEOUT_SECONDS = 3.0
LOCAL_PREDICT_TIMEOUT_SECONDS = 30.0


def _bounded_json_text(text: str) -> str:
    """Limit each remote string by encoded size, including JSON escaping."""
    bounded = text[:MAX_RERANK_TEXT_CHARS]
    while len(json.dumps(bounded, ensure_ascii=False).encode("utf-8")) > MAX_REMOTE_TEXT_BYTES:
        bounded = bounded[: max(0, len(bounded) * 3 // 4)]
    return bounded


class RerankerUnavailable(RuntimeError):
    """The selected reranking model could not return a valid ranking."""


class DocumentReranker:
    """Rank visible passages through one deployment-selected model."""

    def __init__(
        self,
        configuration: RerankerModelConfiguration | None,
        local_factory: Callable[[], Any],
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._configuration = configuration
        self._local_factory = local_factory
        self._local_model: Any | None = None
        self._local_lock = Lock()
        self._local_slots = asyncio.Semaphore(4)
        self._client = client
        if configuration is not None and self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=3.0, pool=3.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                follow_redirects=False,
            )

    @property
    def model_name(self) -> str:
        if self._configuration is not None:
            return self._configuration.name
        return "local-crossencoder"

    async def close(self) -> None:
        """Release the shared remote connection pool during application shutdown."""
        if self._client is not None:
            await self._client.aclose()

    async def rank(self, query: str, documents: Sequence[str], top_n: int) -> list[int]:
        """Return ranked input indices using bounded model batches."""
        if not 0 < top_n <= len(documents):
            raise ValueError("Invalid reranking candidate count")
        bounded_query = query[:MAX_RERANK_TEXT_CHARS]
        ranked: list[tuple[int, float]] = []
        for offset in range(0, len(documents), MAX_RERANK_CANDIDATES):
            batch = documents[offset : offset + MAX_RERANK_CANDIDATES]
            if self._configuration is None:
                scored = await self._score_local_async(bounded_query, batch)
            else:
                scored = await self._score_remote(bounded_query, batch)
            ranked.extend((offset + index, score) for index, score in scored)
        return [index for index, _ in sorted(ranked, key=lambda pair: pair[1], reverse=True)[:top_n]]

    async def _score_local_async(self, query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
        try:
            await asyncio.wait_for(self._local_slots.acquire(), timeout=LOCAL_QUEUE_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise RerankerUnavailable("Local reranker queue is full") from error

        bounded_documents = [content[:MAX_RERANK_TEXT_CHARS] for content in documents]
        task = asyncio.create_task(asyncio.to_thread(self._score_local, query, bounded_documents))

        def release_slot(finished: asyncio.Task[list[tuple[int, float]]]) -> None:
            self._local_slots.release()
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(release_slot)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=LOCAL_PREDICT_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise RerankerUnavailable("Local reranker timed out") from error

    def _score_local(self, query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
        try:
            with self._local_lock:
                if self._local_model is None:
                    self._local_model = self._local_factory()
                model = self._local_model
            if model is None:
                raise ValueError("Local reranker model is missing")
            scores = model.predict([(query, content) for content in documents])
            if len(scores) != len(documents) or any(not math.isfinite(float(score)) for score in scores):
                raise ValueError("Invalid local reranking scores")
            return [(index, float(score)) for index, score in enumerate(scores)]
        except Exception as error:
            raise RerankerUnavailable("Local reranker unavailable") from error

    async def _score_remote(self, query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
        configuration = self._configuration
        client = self._client
        assert configuration is not None and client is not None
        try:
            key = api_key_for_role("reranker")
        except ValueError as error:
            raise RerankerUnavailable("Remote reranker unavailable") from error
        payload = {
            "model": configuration.name,
            "query": _bounded_json_text(query),
            "documents": [_bounded_json_text(content) for content in documents],
            "top_n": len(documents),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_RERANK_BODY_BYTES:
            raise RerankerUnavailable("Remote reranker request exceeds size limit")
        try:
            request = client.build_request(
                "POST",
                f"{str(configuration.settings.base_url).rstrip('/')}/rerank",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                },
                content=body,
            )
            async with asyncio.timeout(REMOTE_TOTAL_TIMEOUT_SECONDS):
                response = await client.send(request, stream=True)
                try:
                    response.raise_for_status()
                    if int(response.headers.get("content-length", "0")) > MAX_RERANK_BODY_BYTES:
                        raise RerankerUnavailable("Remote reranker response exceeds size limit")
                    content = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        content.extend(chunk)
                        if len(content) > MAX_RERANK_BODY_BYTES:
                            raise RerankerUnavailable("Remote reranker response exceeds size limit")
                    results = json.loads(content)["results"]
                finally:
                    await response.aclose()
            if not isinstance(results, list) or len(results) != len(documents):
                raise ValueError("Invalid remote reranking results")
            seen: set[int] = set()
            ranked: list[tuple[int, float]] = []
            for item in results:
                index, score = item["index"], item["relevance_score"]
                if type(index) is not int or not 0 <= index < len(documents) or index in seen:
                    raise ValueError("Invalid remote reranking index")
                if type(score) not in (int, float) or not math.isfinite(score):
                    raise ValueError("Invalid remote reranking score")
                seen.add(index)
                ranked.append((index, score))
            return ranked
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError) as error:
            raise RerankerUnavailable("Remote reranker unavailable") from error
