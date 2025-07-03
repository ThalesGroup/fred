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
from langchain_core.messages.ai import AIMessage
from fred.monitoring.logging_context import get_logging_context
from fred.monitoring.node_monitoring.node_metric_type import NodeMetric
from fred.monitoring.node_monitoring.node_metric_store import get_node_metric_store

logger = logging.getLogger(__name__)

def extract_all_aimessages_from_result(result):
    """
    Returns a flat list of AIMessage objects to monitor.
    Covers:
    - Single AIMessage
    - Dict with 'raw_response': AIMessage
    - Dict with 'raw_response': [AIMessage, ...]
    - Dict with 'messages': [AIMessage, ...]
    """
    if result is None:
        return []

    # Direct AIMessage
    if hasattr(result, "response_metadata") and hasattr(result, "usage_metadata"):
        return [result]

    # Dict with 'raw_response'
    if isinstance(result, dict) and "raw_response" in result:
        raw = result["raw_response"]
        if isinstance(raw, list):
            return [msg for msg in raw if hasattr(msg, "response_metadata")]
        if hasattr(raw, "response_metadata"):
            return [raw]

    # Dict with 'messages'
    if isinstance(result, dict) and "messages" in result:
        messages = result.get("messages", [])
        return [msg for msg in messages if hasattr(msg, "response_metadata")]

    return []

def extract_metadata(msg):
    """
    Extract response_metadata and usage_metadata from an AIMessage.
    Assumes msg is already an AIMessage.
    """
    response_metadata = getattr(msg, "response_metadata", {}) or {}
    usage_metadata = getattr(msg, "usage_metadata", {}) or {}
    return response_metadata, usage_metadata



def monitor_node(func):
    """
    Decorator to automatically record metrics for a LangGraph node function.

    Supports both sync and async functions.
    Records:
    - Execution latency
    - Node function name
    - User/session IDs from logging context
    - Agent/model information (if available)
    - Token usage details (if available)

    Persists metrics to the configured NodeMetricStore.
    """
    if getattr(func, "_is_monitored", False):
        logger.info(f"Node '{func.__name__}' is already monitored.")
        return func

    metric_store = get_node_metric_store()

    def log_metrics(node_name, result, latency):
        ctx = get_logging_context()
        metrics_to_store = []

        # ✅ Get all AIMessages from the result in any supported shape
        messages = extract_all_aimessages_from_result(result)

        if messages:
            for idx, msg in enumerate(messages):
                response_metadata, usage_metadata = extract_metadata(msg)
                response_metadata_with_id = {**response_metadata, "id": getattr(msg, "id", None)}

                metric = NodeMetric(
                    timestamp=time.time(),
                    node_name=f"{node_name}[msg-{idx}]",
                    latency=latency,
                    user_id=ctx.get("user_id", "unknown-user"),
                    session_id=ctx.get("session_id", "unknown-session"),
                    agent_name=ctx.get("agent_name", "unknown-agent_name"),
                    model_name=response_metadata.get("model_name"),
                    input_tokens=usage_metadata.get("input_tokens"),
                    output_tokens=usage_metadata.get("output_tokens"),
                    total_tokens=usage_metadata.get("total_tokens"),
                    metadata=response_metadata_with_id,
                )
                metrics_to_store.append(metric)
        else:
            # Fallback: try to get response_metadata if it exists on the object
            try:
                fallback_metadata = getattr(result, "response_metadata", {}) or {}
            except Exception as e:
                logger.warning(f"[MONITOR] Failed to extract response_metadata from fallback object: {e}")
                fallback_metadata = {}
            metric = NodeMetric(
                timestamp=time.time(),
                node_name=node_name,
                latency=latency,
                user_id=ctx.get("user_id", "unknown-user"),
                session_id=ctx.get("session_id", "unknown-session"),
                agent_name=ctx.get("agent_name", "unknown-agent_name"),
                model_name=None,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                metadata=result,
            )
            metric_store.add_metric(metric)

            logger.info(f"Node '{node_name}' completed in {latency:.2f}s - Metric : {metric}")

            metrics_to_store.append(metric)

        for m in metrics_to_store:
            metric_store.add_metric(m)
        logger.info(f"Node '{node_name}' completed in {latency:.2f}s - Metrics to store = {metrics_to_store}")

    async def _run_async(*args, **kwargs):
        node_name = func.__name__
        logger.info(f"Node '{node_name}' started with args: {args}, kwargs: {kwargs}")
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            latency = time.perf_counter() - start
            log_metrics(node_name, result, latency)
            return result
        except Exception as e:
            latency = time.perf_counter() - start
            logger.exception(f"Node '{node_name}' failed in {latency:.2f}s with error: {e}")
            raise

    def _run_sync(*args, **kwargs):
        node_name = func.__name__
        logger.info(f"Node '{node_name}' started with args: {args}, kwargs: {kwargs}")
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            latency = time.perf_counter() - start
            log_metrics(node_name, result, latency)
            return result
        except Exception as e:
            latency = time.perf_counter() - start
            logger.exception(f"Node '{node_name}' failed in {latency:.2f}s with error: {e}")
            raise

    wrapper = _run_async if inspect.iscoroutinefunction(func) else _run_sync
    functools.update_wrapper(wrapper, func)
    wrapper._is_monitored = True
    return wrapper
