# chat/adapters/message_parts.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import json
from typing import Any, List, Optional

from pydantic import ValidationError

from app.core.chatbot.chat_schema import (
    MessagePart,
    TextPart,
    CodePart,
    ImageUrlPart,
    LinkPart,
    GeoPart,
    ChatTokenUsage,
    FinishReason,
)


# -------------------------------------------------------------------
# Content -> MessageParts
# -------------------------------------------------------------------


def parts_from_raw_content(raw: Any) -> List[MessagePart]:
    """
    Purpose:
      Convert LangChain/OpenAI-style content into v2 `MessagePart` models.

    Supports:
      - plain text (string)
      - list of dicts with {"type": "text" | "input_text" | "image_url"}
      - multi-line text as CodePart
      - fallback: stringify unknown objects as TextPart

    Rationale:
      Keep deterministic and pure — no side effects, no I/O.
    """
    parts: List[MessagePart] = []
    if raw is None:
        return parts

    if isinstance(raw, str):
        if raw.strip():
            parts.append(TextPart(text=raw))
        return parts

    if isinstance(raw, list):
        for itm in raw:
            if not isinstance(itm, dict):
                continue
            t = itm.get("type")
            if t in ("text", "input_text"):
                txt = itm.get("text") or itm.get("input_text")
                if txt:
                    parts.append(TextPart(text=str(txt)))
            elif t == "image_url":
                url = (itm.get("image_url") or {}).get("url")
                if url:
                    parts.append(ImageUrlPart(url=url))
            elif (
                t == "input_text"
                and isinstance(itm.get("text"), str)
                and "\n" in itm["text"]
            ):
                parts.append(CodePart(code=itm["text"]))
        return parts

    # Fallback: dump as string
    parts.append(TextPart(text=str(raw)))
    return parts


# -------------------------------------------------------------------
# Hydrate agent-provided fred_parts (links, maps, future extensions)
# -------------------------------------------------------------------


def hydrate_fred_parts(additional_kwargs: dict) -> List[MessagePart]:
    """
    Purpose:
      Agents (e.g., Rico) can emit structured UI payloads (LinkPart, GeoPart…)
      under `additional_kwargs["fred_parts"]`. This function hydrates them into
      typed Pydantic parts.

    Behavior:
      - Ignores malformed or unknown parts (forward-compat).
      - Returns a flat list of MessagePart instances.
    """
    parts: List[MessagePart] = []
    if not additional_kwargs:
        return parts

    raw_parts = additional_kwargs.get("fred_parts") or []
    for raw in raw_parts:
        if not isinstance(raw, dict):
            continue
        t = raw.get("type")
        try:
            if t == "link":
                parts.append(LinkPart(**raw))
            elif t == "geo":
                parts.append(GeoPart(**raw))
        except ValidationError:
            continue
    return parts


# -------------------------------------------------------------------
# Tool calls (LangChain/OpenAI style) -> normalized dicts
# -------------------------------------------------------------------


def extract_tool_calls(msg: Any) -> List[dict]:
    """
    Normalize tool calls from AIMessage.

    Handles:
      - OpenAI style: msg.tool_calls or msg.additional_kwargs['tool_calls']
      - Each call is normalized into {call_id, name, args: dict}

    Rationale:
      Keep UI layer agnostic of provider-specific shapes.
    """
    calls = []
    tc = getattr(msg, "tool_calls", None)
    if not tc:
        add = getattr(msg, "additional_kwargs", {}) or {}
        tc = add.get("tool_calls")
    if not tc:
        return calls

    for i, c in enumerate(tc):
        cid = c.get("id") or f"t{i + 1}"
        if "function" in c:  # OpenAI function call style
            fn = c["function"] or {}
            name = fn.get("name") or "unnamed"
            args_raw = fn.get("arguments")
        else:
            name = c.get("name") or "unnamed"
            args_raw = c.get("args")

        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except Exception:
                args = {"_raw": args_raw}
        elif isinstance(args_raw, dict):
            args = args_raw
        else:
            args = {"_raw": args_raw}

        calls.append({"call_id": cid, "name": name, "args": args})
    return calls


# -------------------------------------------------------------------
# Metadata coercion
# -------------------------------------------------------------------


def clean_token_usage(raw: dict | None) -> Optional[ChatTokenUsage]:
    """
    Normalize usage metadata into ChatTokenUsage.
    Returns None if parsing fails or input is empty.
    """
    if not raw:
        return None
    try:
        return ChatTokenUsage(
            input_tokens=int(raw.get("input_tokens", 0) or 0),
            output_tokens=int(raw.get("output_tokens", 0) or 0),
            total_tokens=int(raw.get("total_tokens", 0) or 0),
        )
    except Exception:
        return None


def coerce_finish_reason(val: Any) -> Optional[FinishReason]:
    """
    Coerce arbitrary provider finish_reason values into our enum.
    Falls back to FinishReason.other on failure.
    """
    if val is None:
        return None
    try:
        return FinishReason(str(val))
    except Exception:
        return FinishReason.other
