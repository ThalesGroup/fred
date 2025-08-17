from __future__ import annotations
from typing import Any, Dict
from datetime import datetime, timezone

from app.core.chatbot.chat_schema import (
    ChatMessagePayload,
    ChatMessageMetadata,
    ChatTokenUsage,
)


def truncate_datetime(dt: datetime, precision: str) -> datetime:
    dt = dt.astimezone(timezone.utc)  # ensure UTC
    if precision == "minute":
        return dt.replace(second=0, microsecond=0)
    elif precision == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    elif precision == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif precision == "second":
        return dt.replace(microsecond=0)
    else:
        raise ValueError(f"Unsupported precision: {precision}")


def _flatten_token_usage(tu: ChatTokenUsage | Dict[str, Any] | None) -> Dict[str, int]:
    if tu is None:
        return {}
    if isinstance(tu, ChatTokenUsage):
        return {
            "input_tokens": tu.input_tokens,
            "output_tokens": tu.output_tokens,
            "total_tokens": tu.total_tokens,
        }
    # legacy dict path
    return {
        "input_tokens": int(tu.get("input_tokens", 0) or 0),
        "output_tokens": int(tu.get("output_tokens", 0) or 0),
        "total_tokens": int(tu.get("total_tokens", 0) or 0),
    }


def flatten_message(msg: ChatMessagePayload) -> Dict[str, Any]:
    """
    Produce a JSON/analytics-friendly dict from ChatMessagePayload:
    - Datetime -> ISO-8601 string
    - Enums -> str values
    - Metadata -> flattened core fields (+ token usage + sources_count)
    """
    flat: Dict[str, Any] = {
        "timestamp": msg.timestamp.isoformat(),                         # datetime -> str
        "session_id": msg.session_id,
        "exchange_id": msg.exchange_id,
        "type": (msg.type.value if hasattr(msg.type, "value") else str(msg.type)),
        "sender": (msg.sender.value if hasattr(msg.sender, "value") else str(msg.sender)),
        "rank": msg.rank,
        "subtype": (msg.subtype.value if msg.subtype else None),
    }

    md = msg.metadata

    # New typed path: ChatMessageMetadata
    if isinstance(md, ChatMessageMetadata):
        if md.model is not None:
            flat["model"] = md.model
        if md.latency_seconds is not None:
            flat["latency_seconds"] = md.latency_seconds
        if md.agent_name is not None:
            flat["agent_name"] = md.agent_name
        if md.finish_reason is not None:
            flat["finish_reason"] = md.finish_reason
        flat.update(_flatten_token_usage(md.token_usage))
        flat["sources_count"] = len(md.sources) if md.sources is not None else 0

    # Legacy path: metadata came as a dict (older records)
    elif isinstance(md, dict):
        if isinstance(md.get("model"), str):
            flat["model"] = md["model"]
        if isinstance(md.get("latency_seconds"), (int, float)):
            flat["latency_seconds"] = md["latency_seconds"]
        if isinstance(md.get("agent_name"), str):
            flat["agent_name"] = md["agent_name"]
        fr = md.get("finish_reason")
        if isinstance(fr, str):
            flat["finish_reason"] = fr
        flat.update(_flatten_token_usage(md.get("token_usage")))
        sources = md.get("sources") or []
        flat["sources_count"] = len(sources) if isinstance(sources, list) else 0

    # Drop Nones for cleaner docs
    return {k: v for k, v in flat.items() if v is not None}
