from app.core.chatbot.chat_schema import ChatMessagePayload
from datetime import datetime

def truncate_datetime(dt: datetime, precision: str) -> datetime:
    if precision == "minute":
        return dt.replace(second=0, microsecond=0)
    elif precision == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    elif precision == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
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

    # Ajout des champs de metadata en top-level
    for k, v in (msg.metadata or {}).items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                flat[f"{k}.{sub_k}"] = sub_v
        else:
            flat[k] = v

    return flat
