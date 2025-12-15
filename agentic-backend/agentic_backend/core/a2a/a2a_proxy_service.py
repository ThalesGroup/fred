# Copyright Thales 2025
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

import logging
import json
from typing import AsyncIterator, Optional, Tuple, cast
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.client.errors import (
    A2AClientHTTPError,
    A2AClientJSONError,
    A2AClientJSONRPCError,
)
from a2a.types import (
    AgentCard,
    JSONRPCErrorResponse,
    MessageSendParams,
    Part,
    Role,
    SendStreamingMessageSuccessResponse,
    SendMessageRequest,
    TextPart,
    SendStreamingMessageResponse,
)
from a2a.types import Message as A2AMessage
from a2a.utils.constants import EXTENDED_AGENT_CARD_PATH
from httpx_sse import aconnect_sse

logger = logging.getLogger(__name__)


class A2AProxyService:
    """
    Lightweight client wrapper that:
      - Fetches/caches an AgentCard (public, then optional extended)
      - Reuses a single httpx.AsyncClient for A2A traffic
      - Provides convenience helpers to send or stream a simple user text message
    """

    def __init__(
        self,
        *,
        base_url: str,
        extended_card_token: Optional[str] = None,
        timeout_seconds: float = 20.0,
        force_disable_streaming: bool = False,
    ):
        self.base_url, self._card_path = self._split_discovery_url(base_url)
        self.extended_card_token = extended_card_token
        self.timeout_seconds = timeout_seconds
        self._agent_card: Optional[AgentCard] = None
        self._httpx_client: Optional[httpx.AsyncClient] = None
        self._streaming_allowed: Optional[bool] = (
            None if not force_disable_streaming else False
        )

    async def _get_httpx_client(self) -> httpx.AsyncClient:
        if self._httpx_client is None or self._httpx_client.is_closed:
            self._httpx_client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._httpx_client

    @staticmethod
    def _split_discovery_url(url: str) -> Tuple[str, str]:
        """
        Accept either a base URL (http://host:port) or a full discovery URL ending in /.well-known/agent-card.json.
        Returns (base_url_without_trailing_slash, relative_card_path).
        """
        cleaned = url.strip()
        default_path = ".well-known/agent-card.json"
        marker = "/.well-known/agent-card.json"
        if marker in cleaned:
            idx = cleaned.find(marker)
            base = cleaned[:idx] or cleaned
            path = cleaned[idx + 1 :]  # drop leading slash
            return base.rstrip("/"), path
        return cleaned.rstrip("/"), default_path

    async def _fetch_agent_card(self) -> AgentCard:
        """
        Resolve the agent card once; prefer extended card if advertised and token provided.
        """
        if self._agent_card is not None:
            return self._agent_card

        client = await self._get_httpx_client()
        resolver = A2ACardResolver(httpx_client=client, base_url=self.base_url)

        logger.info("[AGENT][A2A] Fetching public agent card from %s", self.base_url)
        try:
            card = await resolver.get_agent_card(relative_card_path=self._card_path)
        except A2AClientJSONError:
            # Fallback for agents that use "protocolVersion" instead of "version"
            logger.info(
                "[AGENT][A2A] Card validation failed; attempting fallback mapping (protocolVersion -> version)"
            )
            resp = await client.get(f"{self.base_url}/{self._card_path}")
            resp.raise_for_status()
            data = resp.json()
            if "version" not in data and data.get("protocolVersion"):
                data["version"] = data["protocolVersion"]
            card = AgentCard.model_validate(data)

        if card.supports_authenticated_extended_card and self.extended_card_token:
            try:
                logger.info(
                    "[AGENT][A2A] Attempting to fetch authenticated extended card from %s%s",
                    self.base_url,
                    EXTENDED_AGENT_CARD_PATH,
                )
                card = await resolver.get_agent_card(
                    relative_card_path=EXTENDED_AGENT_CARD_PATH,
                    http_kwargs={
                        "headers": {
                            "Authorization": f"Bearer {self.extended_card_token}"
                        }
                    },
                )
            except Exception:
                logger.exception(
                    "[AGENT][A2A] Failed to fetch extended agent card; falling back to public card"
                )

        self._agent_card = card
        # Cache the operational URL from the card; discovery URL (self.base_url) may differ.
        if card.url:
            self._operational_url = card.url.rstrip("/")
        self._streaming_allowed = bool(
            getattr(card, "capabilities", None)
            and getattr(card.capabilities, "streaming", False)
        )
        return card

    async def _get_client(self) -> A2AClient:
        card = await self._fetch_agent_card()
        client = await self._get_httpx_client()
        return A2AClient(httpx_client=client, agent_card=card)

    def supports_streaming(self) -> bool:
        return bool(self._streaming_allowed)

    def disable_streaming(self) -> None:
        """Force-disable streaming attempts (e.g., when an upstream agent misreports capabilities)."""
        self._streaming_allowed = False

    async def send_text(
        self,
        *,
        text: str,
        user_id: str,
        context_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        """
        Send a single text message to the A2A agent (non-streaming).
        """
        client = await self._get_client()
        http_kwargs = (
            {"headers": {"Authorization": f"Bearer {access_token}"}}
            if access_token
            else None
        )
        params = MessageSendParams(
            message=A2AMessage(
                role=Role.user,
                parts=[Part(root=TextPart(text=text))],
                message_id=uuid4().hex,
                context_id=context_id,
                metadata={"userId": user_id},
            )
        )
        request = SendMessageRequest(id=str(uuid4()), params=params)
        return await client.send_message(request, http_kwargs=http_kwargs)

    async def stream_text(
        self,
        *,
        text: str,
        user_id: str,
        context_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> AsyncIterator[object]:
        """
        Stream a text message to the A2A agent, yielding NDJSON-friendly chunks.
        """
        # Always fetch the agent card first so capabilities are known before deciding.
        await self._fetch_agent_card()
        streaming = self.supports_streaming()
        # Operations should use the URL advertised by the agent card when available.
        op_base = getattr(self, "_operational_url", None) or self.base_url
        params = MessageSendParams(
            message=A2AMessage(
                role=Role.user,
                parts=[Part(root=TextPart(text=text))],
                message_id=uuid4().hex,
                context_id=context_id,
                metadata={"userId": user_id},
            )
        )
        if streaming:
            logger.info(
                "[AGENT][A2A] Using streaming endpoint for agent=%s", self.base_url
            )
            try:
                httpx_client = await self._get_httpx_client()
                payload = {
                    "jsonrpc": "2.0",
                    "method": "message/stream",
                    "params": params.model_dump(mode="json", exclude_none=True),
                    "id": str(uuid4()),
                }
                headers = {
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                }
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
                async with aconnect_sse(
                    httpx_client,
                    "POST",
                    f"{op_base}/message/stream",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                ) as event_source:
                    event_source.response.raise_for_status()
                    async for sse in event_source.aiter_sse():
                        resp = SendStreamingMessageResponse.model_validate(
                            json.loads(sse.data)
                        )
                        root = resp.root
                        if isinstance(root, JSONRPCErrorResponse):
                            raise A2AClientJSONRPCError(root)
                        success = cast(SendStreamingMessageSuccessResponse, root)
                        yield success.result
                    return
            except A2AClientHTTPError:
                raise
            except Exception as e:
                raise A2AClientHTTPError(
                    400, f"Invalid SSE response or protocol error: {e}"
                ) from e
        else:
            logger.info(
                "[AGENT][A2A] Streaming not advertised; using one-shot send for agent=%s",
                self.base_url,
            )
            client = await self._get_client()
            send_request = SendMessageRequest(id=str(uuid4()), params=params)
            http_kwargs = (
                {"headers": {"Authorization": f"Bearer {access_token}"}}
                if access_token
                else None
            )
            response = await client.send_message(
                send_request, http_kwargs=http_kwargs
            )
            yield response
