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
LangChain-compatible wrapper for monitoring Language Model calls.

This module defines `MonitoredLanguageModel`, a drop-in replacement that wraps
any LangChain-compatible LLM and logs structured monitoring data (latency,
token usage, metadata, etc.) to a `MetricStore` backend.

Metrics are automatically captured and translated from response metadata.
"""



import time
import logging
from typing import Any, List, Optional
from pydantic import Field, PrivateAttr

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from fred.monitoring.hybrid_metric_store import get_metric_store,HybridMetricStore
from fred.monitoring.logging_context import get_logging_context
from fred.monitoring.metric_store import Metric, MetricStore
from fred.monitoring.metric_util import translate_response_metadata_to_metric

logger = logging.getLogger("llm_monitoring")
logger.setLevel(logging.INFO)


class MonitoredLanguageModel(BaseLanguageModel):
    """
    LangChain-compatible LLM wrapper that monitors and logs inference metrics.

    Wraps another LLM (`target`) and automatically tracks:
    - Latency
    - Model name/type
    - User/session context (from `get_logging_context`)
    - Token usage (via `response_metadata`)

    Metrics are translated using `translate_response_metadata_to_metric`
    and stored in the configured `MetricStore` backend.
    
    Attributes:
        target: The underlying LLM to wrap.
        name: Logical name for the wrapped model (used in metrics).
    """
    target: Any = Field(...)
    name: str = Field(default="unnamed")
    _metric_store: HybridMetricStore = PrivateAttr()

    def __init__(self, target: Any, name: str = "unnamed"):
        """
        Initialize the monitored LLM wrapper.

        Args:
            target: A LangChain-compatible language model instance.
            name: Optional label used to identify the model in logs and metrics.
        """
        super().__init__(target=target, name=name)
        self._metric_store = get_metric_store()

    def _llm_type(self) -> str:
        """
        Return the internal type identifier used by LangChain.

        Returns:
            str: A fixed string identifying the wrapper type.
        """
        return "monitoring_wrapper"

    def _log_and_store(self, result: Any, latency: float) -> Optional[Metric]:
        """
        Extract metadata from the result and log it as a `Metric`.

        Args:
            result: The output of the LLM call, expected to have `response_metadata`.
            latency: Duration of the call in seconds.

        Returns:
            Metric | None: The created metric, or None if translation failed.
        """
        ctx = get_logging_context()
        raw_metadata = getattr(result, "response_metadata", {}) or {}

        metric = translate_response_metadata_to_metric(
            raw=raw_metadata,
            ctx=ctx,
            latency=round(latency, 4),
            model_type=self.name,
        )

        if metric:
            logger.info(f"Captured metric: {metric}")
            self._metric_store.add_metric(metric)
        else:
            logger.warning("⚠️ Failed to translate metadata to Metric.")
        return metric

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = self.target.invoke(input, **kwargs)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    async def ainvoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = await self.target.ainvoke(input, **kwargs)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    def predict(self, text: str, stop: Optional[List[str]] = None) -> str:
        start = time.perf_counter()
        result = self.target.predict(text, stop=stop)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    async def apredict(self, text: str, stop: Optional[List[str]] = None) -> str:
        start = time.perf_counter()
        result = await self.target.apredict(text, stop=stop)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    def predict_messages(self, messages: List[BaseMessage], stop: Optional[List[str]] = None) -> BaseMessage:
        start = time.perf_counter()
        result = self.target.predict_messages(messages, stop=stop)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    async def apredict_messages(self, messages: List[BaseMessage], stop: Optional[List[str]] = None) -> BaseMessage:
        start = time.perf_counter()
        result = await self.target.apredict_messages(messages, stop=stop)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    def generate_prompt(self, prompts: List[Any], stop: Optional[List[str]] = None) -> LLMResult:
        start = time.perf_counter()
        result = self.target.generate_prompt(prompts, stop=stop)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    async def agenerate_prompt(self, prompts: List[Any], stop: Optional[List[str]] = None) -> LLMResult:
        start = time.perf_counter()
        result = await self.target.agenerate_prompt(prompts, stop=stop)
        self._log_and_store(result, time.perf_counter() - start)
        return result

    def bind_tools(self, tools: list, *, tool_choice: Optional[str] = None, **kwargs) -> "MonitoredLanguageModel":
        bound = self.target.bind_tools(tools, tool_choice=tool_choice, **kwargs)
        return MonitoredLanguageModel(target=bound, name=self.name)
