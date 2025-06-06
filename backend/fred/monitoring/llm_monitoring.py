# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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
SmartMonitoringWrapper — Universal LangChain instrumentation layer.

This module defines the `SmartMonitoringWrapper` class, a flexible and automatic wrapper
for LangChain components (LLMs, Runnables, functions) that enables:

- Execution time (latency) logging
- Input/output previews
- Token usage and content filtering logs for LLMs
- Context-aware logs using `contextvars` (user/session tracking)

It is designed to be drop-in and compatible with:
- BaseLanguageModel instances (e.g., ChatOpenAI, AzureChatOpenAI)
- LangChain Runnable pipelines (e.g., .with_config(...), .with_structured_output(...))
- Plain async functions used in LangGraph nodes (like "plan" or "execute")
- Synchronous callables

To enable user/session logging context, call `set_logging_context(user_id, session_id)`
at the start of each request.

Example usage:
    wrapper = SmartMonitoringWrapper(my_llm, name="fred-gpt-4o")
    result = await wrapper.ainvoke([...])
"""

import time
from datetime import datetime, timezone
import logging
import inspect
from typing import Any, List, Optional

from langchain_core.language_models import BaseLanguageModel
from langchain_core.runnables import Runnable
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from fred.monitoring.logging_context import get_logging_context


logger = logging.getLogger("llm_monitoring")
logger.setLevel(logging.INFO)

class SmartMonitoringWrapper(Runnable):
    """
    A universal wrapper for LangChain-compatible components that adds monitoring, logging, and latency tracking.

    It supports:
    - BaseLanguageModel instances (e.g., ChatOpenAI)
    - LangChain Runnables (e.g., model.with_structured_output(...))
    - Async functions (e.g., plan, execute nodes)
    - Sync functions (fallback)

    Automatically detects the type of target and applies appropriate invocation logic and logging.
    """
    def __init__(self, target: Any, name: str = "unnamed"):
        """
        Initialize the SmartMonitoringWrapper.

        Args:
            target (Any): A BaseLanguageModel, Runnable, or callable (async/sync) to wrap.
            name (str): A descriptive name for logging and monitoring.
        """
        self.target = target
        self.name = name
        self.type = self._detect_type(target)

    def _detect_type(self, obj:Any)->str:
        """
        Detect the type of the wrapped target to choose correct invocation strategy.

        Returns:
            str: One of 'llm', 'runnable', 'async_fn', 'sync_fn'
        """
        if isinstance(obj, BaseLanguageModel):
            return "llm"
        elif hasattr(obj, "ainvoke") or isinstance(obj, Runnable):
            return "runnable"
        elif inspect.iscoroutinefunction(obj):
            return "async_fn"
        elif callable(obj):
            return "sync_fn"
        else:
            raise TypeError(f"{self.name}: Unsupported type {type(obj)} for SmartMonitoringWrapper")

    async def ainvoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        """
        Asynchronously invoke the wrapped component, timing and logging the call.
        """
        start = time.perf_counter()

        if self.type == "llm":
            result = await self.target.ainvoke(input, **kwargs)
        elif self.type == "runnable":
            result = await self.target.ainvoke(input, config=config, **kwargs)
        elif self.type == "async_fn":
            result = await self.target(input)
        else:
            raise TypeError(f"{self.name}: Cannot async-invoke type '{self.type}'")

        latency = round(time.perf_counter() - start, 3)
        self._log(input, result, latency)
        return result

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        """
        Synchronously invoke the wrapped component, timing and logging the call.
        """
        start = time.perf_counter()

        if self.type == "llm":
            result = self.target.invoke(input, **kwargs)
        elif self.type == "runnable":
            result = self.target.invoke(input, config=config, **kwargs)
        elif self.type == "sync_fn":
            result = self.target(input)
        else:
            raise TypeError(f"{self.name}: Cannot sync-invoke type '{self.type}'")

        latency = round(time.perf_counter() - start, 3)
        self._log(input, result, latency)
        return result

    def _log(self, input: Any, result: Any, latency: float)-> None:
        """
        Log raw response metadata along with minimal context.
        """
        if not isinstance(result, BaseMessage):
            return  # Ignorer les cas sans metadata

        ctx = get_logging_context()
        metadata = getattr(result, "response_metadata", {}) or {}

        metadata.update({
            "user_id": ctx["user_id"],
            "session_id": ctx["session_id"],
            "latency": round(latency, 3),
            "timestamp": time.time(),
            "model_type": self.name,
            "type": self.type,
        })
        logger.info(metadata)

    # Optional passthroughs (if you use it directly as an LLM)
    def predict(self, text: str, stop=None) -> str:
        """
        Pass-through to underlying LLM's synchronous `predict` method.
        """
        return self.target.predict(text, stop=stop)

    async def apredict(self, text: str, stop=None) -> str:
        """
        Pass-through to underlying LLM's asynchronous `apredict` method.
        """
        return await self.target.apredict(text, stop=stop)

    def predict_messages(self, messages, stop=None) -> BaseMessage:
        """
        Pass-through to underlying LLM's `predict_messages` method.
        """
        return self.target.predict_messages(messages, stop=stop)

    async def apredict_messages(self, messages, stop=None) -> BaseMessage:
        """
        Pass-through to underlying LLM's `apredict_messages` method.
        """
        return await self.target.apredict_messages(messages, stop=stop)

    def generate_prompt(self, prompts, stop=None) -> LLMResult:
        """
        Pass-through to underlying LLM's synchronous `generate_prompt` method.
        """
        return self.target.generate_prompt(prompts, stop=stop)

    async def agenerate_prompt(self, prompts, stop=None) -> LLMResult:
        """
        Pass-through to underlying LLM's asynchronous `agenerate_prompt` method.
        """
        return await self.target.agenerate_prompt(prompts, stop=stop)
