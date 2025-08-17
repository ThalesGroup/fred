# langchain_to_payload_utils.py

from collections import defaultdict
import datetime
import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from app.core.chatbot.chat_schema import (
    ChatMessageMetadata,
    ChatMessagePayload,
    ChatTokenUsage,
    FinishReason,
    ImageUrlBlock,
    MessageBlock,
    MessageSubtype,
    MessageType,
    Sender,
    TextBlock,
    ToolResultBlock,
)
from fred_core import VectorSearchHit

logger = logging.getLogger(__name__)


# ---------- Finish reason ----------

def coerce_finish_reason(val: Any) -> Optional[FinishReason]:
    if not isinstance(val, str):
        return None
    v = val.strip()
    if v in {"tool_call", "tool"}:
        return FinishReason.tool_calls
    try:
        return FinishReason(v)  # exact enum value or raises
    except ValueError:
        return FinishReason.other


# ---------- Token usage ----------

def coerce_token_usage(usage_raw: Any) -> Optional[ChatTokenUsage]:
    """
    Convert LangChain/OpenAI-like usage dict to ChatTokenUsage.
    Accepts both {input_tokens, output_tokens, total_tokens} and
    {prompt_tokens, completion_tokens, total_tokens}.
    """
    if not isinstance(usage_raw, dict):
        return None

    # primary keys
    input_tokens = usage_raw.get("input_tokens")
    output_tokens = usage_raw.get("output_tokens")
    total_tokens = usage_raw.get("total_tokens")

    # fallbacks
    if input_tokens is None:
        input_tokens = usage_raw.get("prompt_tokens", 0)
    if output_tokens is None:
        output_tokens = usage_raw.get("completion_tokens", 0)
    if total_tokens is None:
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    return ChatTokenUsage(
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        total_tokens=int(total_tokens or 0),
    )


# ---------- Sources ----------

def coerce_sources(raw: Any) -> List[VectorSearchHit]:
    """Coerce a raw list of dicts/instances to typed VectorSearchHit list."""
    if not isinstance(raw, list):
        return []
    out: List[VectorSearchHit] = []
    for item in raw:
        if isinstance(item, VectorSearchHit):
            out.append(item)
        elif isinstance(item, dict):
            try:
                out.append(VectorSearchHit.model_validate(item))
            except Exception:
                # if one fails, skip rather than crash
                continue
    return out


# ---------- Tool calls ----------

def _parse_json_or_str(s: Any) -> Any:
    if not isinstance(s, str):
        return s
    try:
        return json.loads(s)
    except Exception:
        return s


def extract_tool_call(message: Any) -> Optional[Dict[str, Any]]:
    """
    Extract OpenAI-style function-call info from message.additional_kwargs.tool_calls.
    Returns dict with 'name' and optional 'args' (already parsed), or None.
    """
    ak = getattr(message, "additional_kwargs", {}) or {}
    tc_list = ak.get("tool_calls")
    if not isinstance(tc_list, list) or not tc_list:
        return None
    tc0 = tc_list[0]
    if not isinstance(tc0, dict):
        return None
    fn = tc0.get("function")
    if not isinstance(fn, dict):
        return None
    name = fn.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    args = _parse_json_or_str(fn.get("arguments"))
    return {"name": name, "args": args}


# ---------- Sender / Message type ----------

def coerce_sender(msg: BaseMessage) -> Sender:
    # Map LangChain message classes to your Sender enum
    if isinstance(msg, AIMessage):
        return Sender.assistant
    if isinstance(msg, SystemMessage):
        return Sender.system
    # ToolMessages or unknowns: treat as assistant by default
    return Sender.assistant


# ---------- Blocks & content ----------

def coerce_blocks(raw: Any) -> List[MessageBlock]:
    """
    Normalize LangChain content into structured blocks.
    If raw is a plain string, returns [TextBlock(text=raw)].
    If raw is a list of blocks (dict/str), converts to typed blocks.
    """
    # Plain string
    if isinstance(raw, str):
        return [TextBlock(text=raw)]

    # List of items (LangChain blocky content)
    if isinstance(raw, list):
        out: List[MessageBlock] = []
        for item in raw:
            if isinstance(item, str):
                out.append(TextBlock(text=item))
            elif isinstance(item, dict):
                t = item.get("type")
                if t == "text" and isinstance(item.get("text"), str):
                    out.append(TextBlock(text=item["text"]))
                elif t in {"tool_result", "tool-output"}:
                    name = item.get("name") or item.get("tool_name") or "tool"
                    content = item.get("content")
                    if not isinstance(content, str):
                        content = json.dumps(content, ensure_ascii=False)
                    out.append(ToolResultBlock(name=name, content=content))
                elif t in {"image_url", "image"}:
                    url = item.get("url") or item.get("image_url")
                    if isinstance(url, str):
                        out.append(ImageUrlBlock(url=url, alt=item.get("alt")))
                else:
                    # unknown block -> keep but as text for safety
                    out.append(TextBlock(text=json.dumps(item, ensure_ascii=False)))
            else:
                out.append(TextBlock(text=str(item)))
        return out

    # Unknown type: stringify
    return [TextBlock(text=str(raw))]


def coerce_content(raw: Any) -> str:
    """
    Produce a readable string from structured blocks or a raw string.
    Useful for full-text indexing and legacy renderers.
    """
    blocks = coerce_blocks(raw)
    parts: List[str] = []
    for b in blocks:
        if isinstance(b, TextBlock):
            parts.append(b.text)
        elif isinstance(b, ToolResultBlock):
            parts.append(f"[{b.name} result]\n{b.content}")
        elif isinstance(b, ImageUrlBlock):
            parts.append(f"[image] {b.url}")
        else:
            parts.append(json.dumps(b.model_dump(), ensure_ascii=False))
    return "\n\n".join(parts).strip()


# ---------- Subtype inference ----------

def infer_subtype(
    finish_reason: Optional[FinishReason],
    mtype: MessageType,
    thought: Optional[str | Dict[str, Any]],
) -> Optional[MessageSubtype]:
    if finish_reason == FinishReason.stop:
        return MessageSubtype.final
    if finish_reason == FinishReason.tool_calls or mtype == MessageType.tool:
        return MessageSubtype.tool_result
    if isinstance(thought, (str, dict)) and thought:
        return MessageSubtype.thought
    return None


# chatbot_utils.py


def enrich_chat_message_payloads_with_latencies(
    messages: Iterable[ChatMessagePayload],
    *,
    copy_input: bool = True,
) -> List[ChatMessagePayload]:
    """
    Compute step-to-step latencies (in seconds) within each exchange_id and
    attach them to the *current* message's metadata as `latency_seconds`.

    Ordering inside an exchange is determined by (rank ASC, timestamp ASC).

    Args:
        messages: An iterable of ChatMessagePayload.
        copy_input: If True (default), deep-copies items before mutation;
                    if False, mutates the given message objects.

    Returns:
        A new flat list of ChatMessagePayload with `metadata.latency_seconds` set
        on messages after the first in each exchange.
    """
    # Ensure we work on a list and optionally deep-copy to avoid side-effects
    if copy_input:
        enriched: List[ChatMessagePayload] = [m.model_copy(deep=True) for m in messages]
    else:
        enriched = list(messages)

    # Group by exchange_id
    by_exchange: Dict[str, List[ChatMessagePayload]] = defaultdict(list)
    for m in enriched:
        by_exchange[m.exchange_id].append(m)

    # Compute latencies per exchange
    for ex_id, group in by_exchange.items():
        # Sort stably by (rank, timestamp)
        group.sort(
            key=lambda x: (
                x.rank,
                x.timestamp)
        )

        # For every step after the first, compute latency to previous step
        for i in range(1, len(group)):
            prev_msg = group[i - 1]
            curr_msg = group[i]

            try:
                prev_dt = prev_msg.timestamp 
                curr_dt = curr_msg.timestamp 
            except Exception as e:
                logger.error(
                    "[MetricStore] Timestamp parsing failed for exchange_id %s, ranks %s→%s: %s",
                    ex_id, prev_msg.rank, curr_msg.rank, e,
                )
                continue

            latency = (curr_dt - prev_dt).total_seconds()

            if latency < 0:
                logger.warning(
                    "[MetricStore] Negative latency in exchange_id %s between ranks %s and %s",
                    ex_id, prev_msg.rank, curr_msg.rank,
                )

            # Ensure metadata exists (pydantic provides default, but be safe)
            if curr_msg.metadata is None or not isinstance(curr_msg.metadata, ChatMessageMetadata):
                curr_msg.metadata = ChatMessageMetadata()

            # Record rounded latency; keep raw sign (don’t clamp) so anomalies are visible
            curr_msg.metadata.latency_seconds = round(latency, 4)

    # Flatten back to a list in the original “all messages” order
    # (If you’d rather return in (rank,timestamp) order, you can return
    # sum(by_exchange.values(), []) but that would scramble cross-exchange.)
    return enriched
