# agentic_backend/common/resilient_tool_node.py
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

import anyio
import httpx
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.graph import MessagesState
from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)


def _is_401(exc: BaseException) -> bool:
    seen = set()
    cur: Optional[BaseException] = exc
    while cur and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, httpx.HTTPStatusError):
            try:
                if cur.response is not None and cur.response.status_code == 401:
                    return True
            except Exception:
                logger.warning("Failed to check for 401 status", exc_info=True)
                pass
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    return False


def _get_pending_tool_calls(state: MessagesState) -> List[Dict[str, Any]]:
    messages: List[BaseMessage] = state.get("messages", [])  # type: ignore[assignment]
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            if getattr(m, "tool_calls", None):
                return m.tool_calls  # type: ignore[return-value]
            ak = getattr(m, "additional_kwargs", None) or {}
            if isinstance(ak, dict) and ak.get("tool_calls"):
                return ak["tool_calls"]  # type: ignore[return-value]
            break
    return []


def _log_tools(where: str, tools: list) -> None:
    names = ", ".join(f"{getattr(t, 'name', '?')}@{id(t):x}" for t in tools)
    logger.info("[MCP][ToolNode] %s tools=[%s]", where, names)


def _fallback_as_tool_messages(
    state: MessagesState,
    note: str = "Temporary auth issue. I refreshed my connection. Please retry your request.",
) -> dict:
    pending = _get_pending_tool_calls(state)
    if not pending:
        logger.info(
            "[MCP][ToolNode] fallback: no pending tool_calls; emitting AIMessage"
        )
        return {"messages": [AIMessage(content=note)]}

    ids = ", ".join((p.get("id") or p.get("tool_call_id") or "?") for p in pending)
    logger.info(
        "[MCP][ToolNode] fallback: emitting ToolMessages for tool_calls=[%s]", ids
    )

    tool_msgs: List[ToolMessage] = []
    for tc in pending:
        tc_id = tc.get("id") or tc.get("tool_call_id") or "unknown_call"
        fn = tc.get("function") if isinstance(tc, dict) else None
        name = fn.get("name") if isinstance(fn, dict) else None
        tool_msgs.append(
            ToolMessage(
                content=f"[tool_unavailable] {note}",
                name=name,
                tool_call_id=tc_id,
            )
        )
    return {"messages": tool_msgs}


def make_resilient_tools_node(
    get_tools: Callable[[], list],
    refresh_cb: Callable[[], Awaitable[None]],
    fallback_text: str = (
        "Temporary auth issue while calling backend tools. I refreshed my connection. "
        "Please run your request again."
    ),
    per_call_timeout_s: float = 8.0,
):
    async def _run_once(state: MessagesState, label: str):
        tools = get_tools()
        _log_tools(f"{label}/before_execute", tools)
        node = ToolNode(tools)
        with anyio.move_on_after(per_call_timeout_s) as scope:
            res = await node.ainvoke(state)
        if scope.cancel_called:
            raise TimeoutError(f"ToolNode timed out after {per_call_timeout_s}s")
        return res

    async def _yield_fallback(state: MessagesState) -> dict:
        return _fallback_as_tool_messages(state, note=fallback_text)

    async def _node(state: MessagesState):
        logger.info("[MCP][ToolNode] start")

        try:
            return await _run_once(state, "attempt1")

        except TimeoutError as e:
            logger.warning("[MCP][ToolNode] timeout: %s — refreshing and yielding.", e)
            await refresh_cb()
            _log_tools("after_refresh", get_tools())
            return await _yield_fallback(state)

        except anyio.ClosedResourceError:
            logger.warning(
                "[MCP][ToolNode] stream closed — refreshing and yielding.",
                exc_info=True,
            )
            await refresh_cb()
            _log_tools("after_refresh", get_tools())
            return await _yield_fallback(state)

        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 401:
                logger.warning(
                    "[MCP][ToolNode] 401 Unauthorized — refreshing and yielding.",
                    exc_info=True,
                )
                await refresh_cb()
                _log_tools("after_refresh", get_tools())
                return await _yield_fallback(state)
            logger.error(
                "[MCP][ToolNode] HTTP %s on %s",
                getattr(e.response, "status_code", "?"),
                getattr(getattr(e, "request", None), "url", "?"),
                exc_info=True,
            )
            return await _yield_fallback(state)

        except Exception as e:
            if _is_401(e):
                logger.warning(
                    "[MCP][ToolNode] wrapped 401 — refreshing and yielding.",
                    exc_info=True,
                )
                await refresh_cb()
                _log_tools("after_refresh", get_tools())
                return await _yield_fallback(state)
            logger.exception("[MCP][ToolNode] tool execution error — yielding.")
            return await _yield_fallback(state)

        except BaseException:
            logger.critical(
                "[MCP][ToolNode] non-standard fatal — yielding.", exc_info=True
            )
            return await _yield_fallback(state)

    return _node
