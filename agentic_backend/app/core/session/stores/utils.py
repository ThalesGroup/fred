from app.core.chatbot.chat_schema import ChatMessagePayload
from datetime import datetime, timezone


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


def flatten_message(msg: ChatMessagePayload) -> dict:
    flat = {
        "timestamp": msg.timestamp,
        "session_id": msg.session_id,
        "exchange_id": msg.exchange_id,
        "type": msg.type,
        "sender": msg.sender,
        "rank": msg.rank,
        "subtype": msg.subtype,
    }

    metadata = msg.metadata or {}

    # Safely flatten token_usage if it's a dict
    token_usage = metadata.get("token_usage")
    if isinstance(token_usage, dict):
        for key, value in token_usage.items():
            flat[key] = value

    # Safely include other known fields
    if isinstance(metadata.get("latency_seconds"), (int, float)):
        flat["latency_seconds"] = metadata["latency_seconds"]

    if isinstance(metadata.get("agent_name"), str):
        flat["agent_name"] = metadata["agent_name"]

    if isinstance(metadata.get("model"), str):
        flat["model"] = metadata["model"]

    if isinstance(metadata.get("finish_reason"), str):
        flat["finish_reason"] = metadata["finish_reason"]

    return flat

