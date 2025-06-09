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
smart_monitoring_wrapper.py

A universal monitoring wrapper for LangChain LLMs.

This module defines the `SmartMonitoringWrapper` class, a drop-in wrapper for any
LangChain-compatible `BaseLanguageModel` instance.

Its goal is to transparently enhance LLMs with:

- Execution time measurement (latency logging)
- Structured metadata logging (user/session context)
- Model type tracking
- Token usage monitoring (if metadata is present)
- Full compatibility with LangChain's LLM API

The wrapper supports:
- Sync and async calls (`invoke`, `ainvoke`)
- Prompt and message-based prediction
- Tool binding (for agents/tool-using models)
- Logging to any Python-compatible backend (e.g., console, OpenSearch, etc.)

Usage example:
    monitored_llm = SmartMonitoringWrapper(target=ChatOpenAI(), name="gpt-4")
    result = await monitored_llm.ainvoke("Tell me a joke.")

This wrapper is especially useful for:
- Observability in production
- Debugging and tracking model performance
- Session-aware logging in multi-user systems

It is safe to use in LangGraph agents, LangChain Runnables, or directly in applications.
"""

import time
from datetime import datetime, timezone
import logging
import inspect
from typing import Any, List, Optional
from pydantic import Field,PrivateAttr

from langchain_core.language_models import BaseLanguageModel
from langchain_core.runnables import Runnable
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from fred.monitoring.logging_context import get_logging_context
from fred.monitoring.metric_store import MetricStore



logger = logging.getLogger("llm_monitoring")
logger.setLevel(logging.INFO)

class SmartMonitoringWrapper(BaseLanguageModel):
    """
    A fully compatible wrapper around any BaseLanguageModel that adds intelligent logging and monitoring.
    
    This wrapper captures:
    - Latency (execution time)
    - Contextual metadata (user/session)
    - Model type
    - Token usage (if present in metadata)
    
    It forwards all common methods from LangChain language models to the underlying `target` model.
    """
    target: Any = Field(...)
    name: str = Field(default="unnamed")
    _metric_store: MetricStore = PrivateAttr()

    def __init__(self, target: Any, name: str = "unnamed", metric_store: Optional[MetricStore] = None):
        super().__init__(target=target, name=name)
        self._metric_store = metric_store or MetricStore()

    def _llm_type(self) -> str:
        return "smart_monitoring_wrapper"

    def _log(self, input: Any, result: Any, latency: float) -> dict:
        """
        Extract and log metadata from the result object.
        Returns a dict of structured metadata for optional in-memory storage.
        """
        ctx = get_logging_context()
        metadata = getattr(result, "response_metadata", {}) or {}

        metadata.update({
            "user_id": ctx.get("user_id", "unknown"),
            "session_id": ctx.get("session_id", "unknown"),
            "latency": round(latency, 3),
            "timestamp": time.time(),
            "model_type": self.name,
        })
        logger.info(metadata)
        return metadata

    def _store_metric(self, metadata: dict, persist: bool = False):
        if self._metric_store:
            self._metric_store.add_metric(metadata)
            if persist:
                self._metric_store.save_to_file("fred/monitoring/logs/monitoring_logs.jsonl")

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        """
        Synchronous invocation of the underlying model with logging.
        """
        start = time.perf_counter()
        result = self.target.invoke(input, **kwargs)
        metadata = self._log(input, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result

    async def ainvoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        """
        Asynchronous invocation of the underlying model with logging.
        """
        start = time.perf_counter()
        result = await self.target.ainvoke(input, **kwargs)
        metadata = self._log(input, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result

    def bind_tools(self, tools: list, *, tool_choice: Optional[str] = None, **kwargs) -> "SmartMonitoringWrapper":
        """
        Binds tools to the underlying model and returns a new wrapped instance.
        """
        bound = self.target.bind_tools(tools, tool_choice=tool_choice, **kwargs)
        return SmartMonitoringWrapper(target=bound, name=self.name)

    def predict(self, text: str, stop: Optional[List[str]] = None) -> str:
        """
        Synchronous text prediction with logging.
        """
        start = time.perf_counter()
        result = self.target.predict(text, stop=stop)
        metadata = self._log(text, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result

    async def apredict(self, text: str, stop: Optional[List[str]] = None) -> str:
        """
        Asynchronous text prediction with logging.
        """
        start = time.perf_counter()
        result = await self.target.apredict(text, stop=stop)
        metadata = self._log(text, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result

    def predict_messages(self, messages: List[BaseMessage], stop: Optional[List[str]] = None) -> BaseMessage:
        """
        Synchronous message-based prediction with logging.
        """
        start = time.perf_counter()
        result = self.target.predict_messages(messages, stop=stop)
        metadata = self._log(messages, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result

    async def apredict_messages(self, messages: List[BaseMessage], stop: Optional[List[str]] = None) -> BaseMessage:
        """
        Asynchronous message-based prediction with logging.
        """
        start = time.perf_counter()
        result = await self.target.apredict_messages(messages, stop=stop)
        metadata = self._log(messages, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result

    def generate_prompt(self, prompts: List[Any], stop: Optional[List[str]] = None) -> LLMResult:
        """
        Synchronous prompt generation with logging.
        """
        start = time.perf_counter()
        result = self.target.generate_prompt(prompts, stop=stop)
        metadata = self._log(prompts, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result

    async def agenerate_prompt(self, prompts: List[Any], stop: Optional[List[str]] = None) -> LLMResult:
        """
        Asynchronous prompt generation with logging.
        """
        start = time.perf_counter()
        result = await self.target.agenerate_prompt(prompts, stop=stop)
        metadata = self._log(prompts, result, time.perf_counter() - start)
        self._store_metric(metadata, persist=True)
        return result
