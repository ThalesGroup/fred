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
monitor_node.py

This module defines a decorator to transparently monitor LangGraph node executions.
It records latency, user/session context, model info, and token usage as NodeMetric entries.

Features:
- Works on both sync and async node functions.
- Automatically enriches metrics with request context.
- Persists metrics via NodeMetricStore.
"""

import time
import logging
import functools
import inspect

from app.core.monitoring.logging_context import get_logging_context
from app.core.monitoring.node_monitoring.node_metric_store import get_node_metric_store
from app.core.monitoring.node_monitoring.node_metric_type import NodeMetric

logger = logging.getLogger(__name__)


def monitor_node(func):
    """
    Decorator to automatically record metrics for a LangGraph node function.

    Supports both sync and async functions.
    Records:
    - Execution latency
    - Node function name
    - User/session IDs from logging context
    - Agent/model information
    - Token usage details

    Persists metrics to the configured NodeMetricStore.
    """
    if getattr(func, "_is_monitored", False):
        logger.info(f"Node '{func.__name__}' is already monitored.")
        return func

    metric_store = get_node_metric_store()

    async def _run_async(*args, **kwargs):
        node_name = func.__name__
        logger.info(f"Node '{node_name}' started with args: {args}, kwargs: {kwargs}")
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            latency = time.perf_counter() - start

            ctx = get_logging_context()
            ai_message = (result.get("messages") or [{}])[0]
            message = ai_message.__dict__
            response_metadata = message.get("response_metadata", {})
            usage_metadata = message.get("usage_metadata", {})

            metric = NodeMetric(
                timestamp=time.time(),
                node_name=node_name,
                latency=latency,
                user_id=ctx.get("user_id", "unknown-user"),
                session_id=ctx.get("session_id", "unknown-session"),
                agent_name=ctx.get("agent_name", "unknown-agent_name"),
                model_name=response_metadata.get("model_name"),
                input_tokens=usage_metadata.get("input_tokens"),
                output_tokens=usage_metadata.get("output_tokens"),
                total_tokens=usage_metadata.get("total_tokens"),
                result_summary=str(message.get("content", ""))[:300],
                metadata=result,
            )
            metric_store.add_metric(metric)

            logger.info(
                f"Node '{node_name}' completed in {latency:.2f}s - Metric : {metric}"
            )
            return result

        except Exception as e:
            latency = time.perf_counter() - start
            logger.exception(
                f"Node '{node_name}' failed in {latency:.2f}s with error: {e}"
            )
            raise

    def _run_sync(*args, **kwargs):
        node_name = func.__name__
        logger.info(f"Node '{node_name}' started with args: {args}, kwargs: {kwargs}")
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            latency = time.perf_counter() - start

            ctx = get_logging_context()
            message = (result.get("messages") or [{}])[0]
            response_metadata = message.get("response_metadata", {})
            usage = response_metadata.get("token_usage", {})

            metric = NodeMetric(
                timestamp=time.time(),
                node_name=node_name,
                latency=latency,
                user_id=ctx.get("user_id", "unknown-user"),
                session_id=ctx.get("session_id", "unknown-session"),
                agent_name=ctx.get("agent_name", "unknown-agent_name"),
                model_name=response_metadata.get("model_name"),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                result_summary=str(message.get("content", ""))[:300],
                metadata=result,
            )
            metric_store.add_metric(metric)

            logger.info(f"Node '{node_name}' completed in {latency:.2f}s.")
            return result

        except Exception as e:
            latency = time.perf_counter() - start
            logger.exception(
                f"Node '{node_name}' failed in {latency:.2f}s with error: {e}"
            )
            raise

    wrapper = _run_async if inspect.iscoroutinefunction(func) else _run_sync
    functools.update_wrapper(wrapper, func)
    wrapper._is_monitored = True
    return wrapper
