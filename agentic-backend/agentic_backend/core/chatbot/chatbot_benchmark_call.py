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

import asyncio
import logging
import time
from datetime import datetime
from typing import Awaitable, Callable, cast
from uuid import uuid4

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fred_core import decode_jwt
from fred_core.kpi import KPIActor
from langchain_core.messages import HumanMessage
from pydantic import TypeAdapter, ValidationError

from agentic_backend.application_context import (
    get_app_context,
    get_default_chat_model,
)
from agentic_backend.core.chatbot.chat_schema import (
    ChatAskInput,
    ChatTokenUsage,
    ErrorEvent,
    FinalEvent,
    SessionSchema,
    StreamEvent,
    TextPart,
    make_assistant_final,
    make_user_text,
)

logger = logging.getLogger(__name__)


def burn_cpu_ms(duration_ms: int = 200) -> None:
    if duration_ms <= 0:
        return
    deadline = time.perf_counter() + duration_ms / 1000.0
    x = 0
    while time.perf_counter() < deadline:
        x = (x * 3 + 1) % 10000019


def _extract_usage(ai_message) -> ChatTokenUsage:
    """
    Best-effort extraction of token usage from LangChain AIMessage metadata.
    Keeps baseline comparable with main pipeline metrics.
    """
    meta = getattr(ai_message, "response_metadata", {}) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}

    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt_tokens_total")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("completion_tokens_total")
        or 0
    )
    total_tokens = usage.get("total_tokens") or prompt_tokens + completion_tokens

    return ChatTokenUsage(
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


async def handle_chatbot_baseline_websocket(
    websocket: WebSocket,
    *,
    safe_send_text: Callable[[WebSocket, str], Awaitable[bool]],
    summarize_error: Callable[[Exception, str | None], str],
) -> None:
    """
    Minimal LangChain baseline:
      - Reuses the configured default_chat_model (e.g., mock OpenAI via base_url).
      - Hardcodes temperature=0.0.
      - No agent orchestration, RAG, or persistence; one prompt -> one answer.
      - Allows multiple sequential requests on the same WebSocket.

    This is used for benchmarking Fred overhead against a simple direct LLM call.
    The exact same configuration should be used for Fred's default_chat_model
    and for this baseline to ensure comparability.

    What you should expect is this baseline to be faster than Fred that takes care
    of orchestration, RAG, and persistence. The difference in latency and resource
    usage should give you an idea of the overhead introduced by Fred.
    """
    auth = websocket.headers.get("authorization") or ""
    token = (
        auth.split(" ", 1)[1]
        if auth.lower().startswith("bearer ")
        else websocket.query_params.get("token")
    )
    if not token:
        await websocket.close(code=4401)
        return

    try:
        user = decode_jwt(token)
    except HTTPException:
        await websocket.close(code=4401)
        return

    ws_input_adapter = TypeAdapter(ChatAskInput)

    try:
        baseline_model = get_default_chat_model().bind(temperature=0.0)
    except Exception as e:
        summary = summarize_error(e, "BASELINE could not initialize default_chat_model")
        await safe_send_text(
            websocket,
            ErrorEvent(
                type="error", content=summary, session_id="unknown-session"
            ).model_dump_json(),
        )
        await websocket.close(code=1011)
        return

    while True:
        client_request = None
        try:
            client_request = await websocket.receive_json()
            logger.debug("[BASELINE WS] recv payload=%s", client_request)
        except WebSocketDisconnect:
            logger.debug("Client disconnected from baseline WebSocket")
            break
        except Exception as e:
            summary = summarize_error(e, "BASELINE Error reading websocket payload")
            await safe_send_text(
                websocket,
                ErrorEvent(
                    type="error", content=summary, session_id="unknown-session"
                ).model_dump_json(),
            )
            break

        try:
            ask = ws_input_adapter.validate_python(client_request)
        except ValidationError:
            try:
                ask = ChatAskInput(**client_request)
            except Exception as e:
                if isinstance(client_request, dict) and client_request.get("message"):
                    # Minimal fallback: accept {"message": "..."} payloads.
                    msg_value = client_request.get("message")
                    if not isinstance(msg_value, str):
                        summary = summarize_error(
                            ValueError("message must be a string"),
                            "BASELINE Invalid payload",
                        )
                        await safe_send_text(
                            websocket,
                            ErrorEvent(
                                type="error",
                                content=summary,
                                session_id="unknown-session",
                            ).model_dump_json(),
                        )
                        continue
                    msg_value = cast(str, msg_value)
                    session_id = client_request.get("session_id")
                    if session_id is not None:
                        ask = ChatAskInput(
                            agent_id=client_request.get("agent_id")
                            or "openai-baseline",
                            message=msg_value,
                            session_id=session_id,
                            client_exchange_id=client_request.get("client_exchange_id"),
                            type="ask",
                        )
                    else:
                        raise ValueError("Missing session_id in payload")
                else:
                    summary = summarize_error(e, "BASELINE Invalid payload")
                    await safe_send_text(
                        websocket,
                        ErrorEvent(
                            type="error", content=summary, session_id="unknown-session"
                        ).model_dump_json(),
                    )
                    continue

        session_id = ask.session_id or str(uuid4())
        exchange_id = ask.client_exchange_id or str(uuid4())
        base_rank = 0

        user_message = make_user_text(session_id, exchange_id, base_rank, ask.message)
        if not await safe_send_text(
            websocket,
            StreamEvent(type="stream", message=user_message).model_dump_json(),
        ):
            break

        try:
            kpi = get_app_context().get_kpi_writer()
            with kpi.timer(
                "app.phase_latency_ms",
                dims={
                    "agent_id": ask.agent_id or "baseline",
                    "phase": "llm_invoke",
                },
                actor=KPIActor(type="system", user_id=None, groups=None),
                unit="ms",
            ):
                start_ts = datetime.utcnow()
                burn_cpu_ms(60)
                ai_message = await baseline_model.ainvoke(
                    [HumanMessage(content=ask.message)]
                )
                latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
        except asyncio.CancelledError:
            logger.error(
                "[BASELINE] CancelledError (likely client disconnected) session_id=%s",
                session_id,
            )
            raise
        except Exception as e:
            summary = summarize_error(e, "BASELINE OpenAI call failed")
            if not await safe_send_text(
                websocket,
                ErrorEvent(
                    type="error", content=summary, session_id=session_id
                ).model_dump_json(),
            ):
                break
            continue

        usage = _extract_usage(ai_message)
        model_name = (
            getattr(ai_message, "response_metadata", {}).get("model_name")
            or getattr(ai_message, "response_metadata", {}).get("model")
            or getattr(ai_message, "response_metadata", {}).get("model_name_or_path")
            or getattr(ai_message, "id", None)
            or "unknown"
        )

        assistant_message = make_assistant_final(
            session_id=session_id,
            exchange_id=exchange_id,
            rank=base_rank + 1,
            parts=[TextPart(text=getattr(ai_message, "content", str(ai_message)))],
            model=model_name,
            sources=[],
            usage=usage,
        )
        assistant_message = assistant_message.model_copy(
            update={
                "metadata": assistant_message.metadata.model_copy(
                    update={
                        "latency_ms": latency_ms,
                        "runtime_context": ask.runtime_context,
                    }
                )
            }
        )

        if not await safe_send_text(
            websocket,
            StreamEvent(type="stream", message=assistant_message).model_dump_json(),
        ):
            break

        session = SessionSchema(
            id=session_id,
            user_id=user.uid,
            agent_id=ask.agent_id or "openai-baseline",
            title=ask.message[:80] or "openai-baseline",
            updated_at=datetime.utcnow(),
            next_rank=assistant_message.rank + 1,
        )
        if not await safe_send_text(
            websocket,
            FinalEvent(
                type="final",
                messages=[user_message, assistant_message],
                session=session,
            ).model_dump_json(),
        ):
            break
