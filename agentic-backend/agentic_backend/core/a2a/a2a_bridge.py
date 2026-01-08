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
from datetime import datetime
from typing import Any, AsyncIterator

from agentic_backend.core.a2a.a2a_proxy_service import A2AProxyService
from agentic_backend.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    Role,
    TextPart,
)

logger = logging.getLogger(__name__)


def extract_text_from_a2a_result(result: dict) -> str | None:
    """
    Best-effort extraction of text content from an A2A result payload.
    Supports:
      - result.parts[*].root.text
      - result.history[*].parts[*].root.text
      - result.message.parts[*].root.text
      - result.artifacts[*].parts[*].root.text
      - result.artifact.parts[*].root.text (artifact-update events)
    """

    def _parts_to_text(parts: list) -> list[str]:
        texts = []
        for p in parts:
            root = p.get("root", {})
            if isinstance(root, dict) and root.get("text"):
                texts.append(str(root["text"]))
            elif p.get("text"):
                texts.append(str(p["text"]))
        return texts

    # Some payloads use "artifact" or "artifacts" with plain part objects (no root)
    def _artifact_parts_to_text(result_dict: dict) -> list[str]:
        parts_texts: list[str] = []
        # artifact-update event
        if isinstance(result_dict.get("artifact"), dict):
            parts = result_dict["artifact"].get("parts")
            if isinstance(parts, list):
                parts_texts.extend(_parts_to_text(parts))
        # task with artifacts list
        if isinstance(result_dict.get("artifacts"), list):
            for art in result_dict["artifacts"]:
                if isinstance(art, dict) and isinstance(art.get("parts"), list):
                    parts_texts.extend(_parts_to_text(art["parts"]))
        return parts_texts

    for key in ("parts",):
        if isinstance(result.get(key), list):
            texts = _parts_to_text(result[key])
            if texts:
                return "\n".join(texts)

    if isinstance(result.get("message"), dict):
        parts = result["message"].get("parts")
        if isinstance(parts, list):
            texts = _parts_to_text(parts)
            if texts:
                return "\n".join(texts)

    if isinstance(result.get("history"), list):
        for msg in result["history"]:
            if isinstance(msg, dict) and isinstance(msg.get("parts"), list):
                texts = _parts_to_text(msg["parts"])
                if texts:
                    return "\n".join(texts)

    # Artifacts on task or artifact-update events
    art_texts = _artifact_parts_to_text(result)
    if art_texts:
        return "\n".join(art_texts)
    return None


async def stream_a2a_as_chat_messages(
    *,
    proxy: A2AProxyService,
    user_id: str,
    access_token: str | None = None,
    text: str,
    session_id: str,
    exchange_id: str,
    start_rank: int = 0,
) -> AsyncIterator[ChatMessage]:
    """
    Translate A2A stream results into Fred ChatMessage instances for UI consumption.
    """
    rank = start_rank
    buffer: list[str] = []
    final_sent = False
    async for chunk in proxy.stream_text(
        text=text,
        user_id=user_id,
        context_id=session_id,
        access_token=access_token,
    ):
        logger.info(
            "[AGENT][A2A] Received chunk for session=%s agent=%s raw=%s",
            session_id,
            proxy.base_url,
            getattr(chunk, "model_dump", lambda **_: chunk)(),
        )
        # The A2A client yields Pydantic models; tolerate plain dicts for type checkers.
        if hasattr(chunk, "model_dump"):
            data = chunk.model_dump(exclude_none=True)  # type: ignore[attr-defined]
        elif isinstance(chunk, dict):
            data = chunk
        else:
            logger.info(
                "[AGENT][A2A] Skipping chunk (unsupported type) for session=%s type=%s",
                session_id,
                type(chunk),
            )
            continue
        result = data.get("result") or data
        logger.info(
            "[AGENT][A2A] Parsed result for session=%s keys=%s",
            session_id,
            list(result.keys()),
        )
        txt = extract_text_from_a2a_result(result)
        if not txt:
            logger.info(
                "[AGENT][A2A] Skipping chunk with no text for session=%s result=%s",
                session_id,
                result,
            )
            continue
        buffer.append(txt)

        is_final = bool(result.get("final"))
        status = result.get("status")
        if isinstance(status, dict) and status.get("state") in {
            "completed",
            "succeeded",
        }:
            is_final = True
        if result.get("lastChunk") is True:
            # Treat lastChunk on artifact-update as final content chunk.
            is_final = True

        if is_final:
            combined = "\n".join(buffer)
            logger.info(
                "[AGENT][A2A] Emitting combined assistant message rank=%d session=%s",
                rank,
                session_id,
            )
            yield ChatMessage(
                session_id=session_id,
                exchange_id=exchange_id,
                rank=rank,
                timestamp=datetime.utcnow(),
                role=Role.assistant,
                channel=Channel.final,
                parts=[TextPart(text=combined)],
            )
            final_sent = True
            buffer.clear()
            break

    if buffer and not final_sent:
        combined = "\n".join(buffer)
        logger.info(
            "[AGENT][A2A] Emitting buffered assistant message rank=%d session=%s (no explicit final flag)",
            rank,
            session_id,
        )
        yield ChatMessage(
            session_id=session_id,
            exchange_id=exchange_id,
            rank=rank,
            timestamp=datetime.utcnow(),
            role=Role.assistant,
            channel=Channel.final,
            parts=[TextPart(text=combined)],
        )


def is_a2a_agent(settings: Any) -> bool:
    # Accept either the explicit class path for the stub agent or metadata markers.
    class_path = getattr(settings, "class_path", None) or ""
    meta = getattr(settings, "metadata", None) or {}
    agent_type = getattr(settings, "type", None)
    return (
        agent_type == "a2a_proxy"
        or "a2a_proxy_agent.A2AProxyAgent" in class_path
        or bool(meta.get("a2a_base_url"))
    )


def get_proxy_for_agent(
    app,
    agent_name: str,
    base_url: str,
    token: str | None,
    *,
    force_disable_streaming: bool = False,
) -> A2AProxyService:
    """Cache one proxy per A2A agent on app.state to avoid recreating clients."""
    cache: dict[str, A2AProxyService] = getattr(app.state, "a2a_proxy_services", {})
    if cache and agent_name in cache:
        logger.info(
            "[AGENT][A2A] Reusing cached proxy for agent=%s base_url=%s",
            agent_name,
            base_url,
        )
        svc = cache[agent_name]
        if force_disable_streaming:
            svc.disable_streaming()
        return svc
    logger.info(
        "[AGENT][A2A] Creating proxy for agent=%s base_url=%s", agent_name, base_url
    )
    svc = A2AProxyService(
        base_url=base_url,
        extended_card_token=token,
        force_disable_streaming=force_disable_streaming,
    )
    cache[agent_name] = svc
    app.state.a2a_proxy_services = cache
    return svc
