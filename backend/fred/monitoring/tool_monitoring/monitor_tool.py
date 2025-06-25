import time
import logging
from functools import wraps
import pandas as pd
from fred.monitoring.logging_context import get_logging_context
from fred.monitoring.tool_monitoring.utils import translate_to_metric
from fred.monitoring.tool_monitoring.metric_types import ToolMetric
from fred.monitoring.tool_monitoring.hybrid_tool_metric_store import HybridToolMetricStore,get_tool_metric_store

logger = logging.getLogger(__name__)

def monitor_tool(tool):
    """
    Decorates a BaseTool to log latency, errors, and collect metrics.
    """
    if getattr(tool, "_is_monitored", False):
        logger.info('Tool already monitored')
        return tool

    original_run = getattr(tool, "_run", None)
    original_arun = getattr(tool, "_arun", None)
    
    tool_metric_store = get_tool_metric_store()

    if original_run:
        @wraps(original_run)
        def monitored_run(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = original_run(*args, **kwargs)
                latency = time.perf_counter() - start
                
                ctx = get_logging_context()
                
                tool_metric = ToolMetric(
                    timestamp=time.time(),
                    tool_name=tool.name,
                    latency=latency,
                    user_id=ctx.get("user_id","unknown-user"),
                    session_id=ctx.get("session_id","unknown-session"),
                    )
                tool_metric_store.add_metric(tool_metric)
                logger.info(f"(run) tool metric : {tool_metric}")
                return result
            except Exception as e:
                logger.exception(f"[{tool.name}] failed: {e}")
                raise

        tool._run = monitored_run

    if original_arun:
        @wraps(original_arun)
        async def monitored_arun(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await original_arun(*args, **kwargs)
                latency = time.perf_counter() - start
                
                ctx = get_logging_context()
                
                tool_metric = ToolMetric(
                    timestamp=time.time(),
                    tool_name=tool.name,
                    latency=latency,
                    user_id=ctx.get("user_id","unknown-user"),
                    session_id=ctx.get("session_id","unknown-session"),
                    )
                tool_metric_store.add_metric(tool_metric)
                logger.info(f"(arun) tool metric : {tool_metric}")
                return result
            except Exception as e:
                logger.exception(f"[{tool.name}] async failed: {e}")
                raise

        tool._arun = monitored_arun
        tool._is_monitored = True

    return tool
