from __future__ import annotations

import copy
from typing import Any, Mapping, cast

from agentic_backend.core.agents.runtime_context import RuntimeContext, get_language


def hitl_language_for_agent(
    agent: Any = None,
    *,
    runtime_context: RuntimeContext | None = None,
    default: str = "en",
) -> str:
    """
    Resolve the preferred language for HITL payloads from RuntimeContext.

    Current mapping:
    - fr* -> fr
    - en* -> en
    - others / missing -> `default`
    """
    ctx = runtime_context
    if ctx is None and agent is not None:
        getter = getattr(agent, "get_runtime_context", None)
        if callable(getter):
            try:
                maybe_ctx = getter()
                ctx = maybe_ctx if isinstance(maybe_ctx, RuntimeContext) else None
            except Exception:
                fallback_ctx = getattr(agent, "runtime_context", None)
                ctx = fallback_ctx if isinstance(fallback_ctx, RuntimeContext) else None
        else:
            fallback_ctx = getattr(agent, "runtime_context", None)
            ctx = fallback_ctx if isinstance(fallback_ctx, RuntimeContext) else None

    lang = (
        (get_language(cast(RuntimeContext | None, ctx)) if ctx else "").strip().lower()
    )
    if not lang:
        return default
    if lang.startswith("fr"):
        return "fr"
    if lang.startswith("en"):
        return "en"
    return default


def is_hitl_french(
    agent: Any = None,
    *,
    runtime_context: RuntimeContext | None = None,
) -> bool:
    return hitl_language_for_agent(agent, runtime_context=runtime_context) == "fr"


def select_hitl_payload(
    agent: Any,
    *,
    en: Mapping[str, Any],
    fr: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Return a deep-copied localized payload variant for `interrupt()`.
    """
    payload = fr if is_hitl_french(agent) else en
    return copy.deepcopy(dict(payload))
