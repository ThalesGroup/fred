# app/core/agents/resilient_tools_node.py
from typing import Awaitable, Callable, Optional
import logging

import anyio
import httpx
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import MessagesState

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
                pass
        cur = (getattr(cur, "__cause__", None) or getattr(cur, "__context__", None))
    return False

def make_resilient_tools_node(
    get_tools: Callable[[], list],
    refresh_cb: Callable[[], Awaitable[None]],
    fallback_text: str = (
        "Temporary auth issue while calling backend tools. I refreshed my connection "
        "and retried once, but it still failed. Please try again."
    ),
    per_call_timeout_s: float = 8.0, 
):
    async def _run_once(state: MessagesState):
        node = ToolNode(get_tools())
        res = None
        # Hard timeout so we never hang if the MCP stream is torn down
        with anyio.move_on_after(per_call_timeout_s) as scope:  # ← timeout #1
            res = await node.ainvoke(state)
        if scope.cancel_called:
            raise TimeoutError(f"ToolNode timed out after {per_call_timeout_s}s")
        return res

    async def _node(state: MessagesState):
        logger.info("[MCP][ToolNode] start")

        # First attempt
        try:
            return await _run_once(state)

        except TimeoutError as e:
            logger.warning("[MCP][ToolNode] timeout on first attempt: %s — refreshing and retrying once.", e)
            await refresh_cb()
            try:
                # Second attempt with another timeout window
                node = ToolNode(get_tools())
                res = None
                with anyio.move_on_after(per_call_timeout_s) as scope:  # ← timeout #2
                    res = await node.ainvoke(state)
                if scope.cancel_called:
                    raise TimeoutError(f"ToolNode timed out again after refresh ({per_call_timeout_s}s)")
                return res
            except Exception:
                logger.error("[MCP][ToolNode] retry failed after timeout/refresh.", exc_info=True)
                return {"messages": [AIMessage(content=fallback_text)]}

        except anyio.ClosedResourceError:
            logger.warning("[MCP][ToolNode] stream closed; refreshing and retrying once.", exc_info=True)
            await refresh_cb()
            try:
                return await _run_once(state)
            except Exception:
                logger.error("[MCP][ToolNode] retry failed after stream-closed/refresh.", exc_info=True)
                return {"messages": [AIMessage(content=fallback_text)]}

        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 401:
                logger.warning("[MCP][ToolNode] 401 Unauthorized; refreshing and retrying once.", exc_info=True)
                await refresh_cb()
                try:
                    return await _run_once(state)
                except Exception:
                    logger.error("[MCP][ToolNode] retry failed after 401/refresh.", exc_info=True)
                    return {"messages": [AIMessage(content=fallback_text)]}
            logger.error("[MCP][ToolNode] HTTP %s on %s",
                         getattr(e.response, "status_code", "?"),
                         getattr(getattr(e, "request", None), "url", "?"),
                         exc_info=True)
            return {"messages": [AIMessage(content=fallback_text)]}

        except Exception as e:
            if _is_401(e):
                logger.warning("[MCP][ToolNode] wrapped 401; refreshing and retrying once.", exc_info=True)
                await refresh_cb()
                try:
                    return await _run_once(state)
                except Exception:
                    logger.error("[MCP][ToolNode] retry failed after wrapped-401/refresh.", exc_info=True)
                    return {"messages": [AIMessage(content=fallback_text)]}
            logger.exception("[MCP][ToolNode] tool execution error.")
            return {"messages": [AIMessage(content=fallback_text)]}

        except BaseException:
            logger.critical("[MCP][ToolNode] non-standard fatal; returning fallback.", exc_info=True)
            return {"messages": [AIMessage(content=fallback_text)]}

    return _node