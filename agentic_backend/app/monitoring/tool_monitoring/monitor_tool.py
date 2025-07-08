# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
monitor_tool.py

Defines the monitor_tool decorator to automatically track
tool executions (sync and async) in LangChain or similar frameworks.

Features:
- Records latency.
- Captures user/session from logging context.
- Persists metrics in ToolMetricStore.
- Adds minimal overhead and preserves original signature.
"""


import time
import logging
from functools import wraps
import pandas as pd
from app.monitoring.logging_context import get_logging_context
from app.monitoring.tool_monitoring.tool_metric_type import ToolMetric
from app.monitoring.tool_monitoring.tool_metric_store import ToolMetricStore,get_tool_metric_store

logger = logging.getLogger(__name__)

def monitor_tool(tool):
    """
    Decorator that instruments a BaseTool to log metrics automatically.

    When applied:
    - Wraps _run and _arun methods to measure latency.
    - Captures user/session IDs from logging context.
    - Stores ToolMetric records in ToolMetricStore.

    Args:
        tool: The tool instance to instrument.

    Returns:
        The same tool, with wrapped methods.
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
            logger.info(f"Tool '{tool.name}' started with args: {args}")
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
                logger.info(f"Tool '{tool.name}' completed in {latency:.2f}s with result: {result}")
                return result
            except Exception as e:
                logger.exception(f"[{tool.name}] failed: {e}")
                raise

        tool._run = monitored_run

    if original_arun:
        @wraps(original_arun)
        async def monitored_arun(*args, **kwargs):
            logger.info(f"Tool '{tool.name}' started with args: {args}")
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
                logger.info(f"Tool '{tool.name}' completed in {latency:.2f}s with result: {result}")
                return result
            except Exception as e:
                logger.exception(f"[{tool.name}] async failed: {e}")
                raise

        tool._arun = monitored_arun
        tool._is_monitored = True

    return tool
