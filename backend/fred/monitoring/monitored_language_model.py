# monitoring_wrapper.py

import time
import logging
from typing import Any, List, Optional
from pydantic import Field, PrivateAttr

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from fred.monitoring.inmemory_metric_store import get_metric_store
from fred.monitoring.logging_context import get_logging_context
from fred.monitoring.metric_store import Metric, MetricStore
from fred.monitoring.metric_util import translate_response_metadata_to_metric

logger = logging.getLogger("llm_monitoring")
logger.setLevel(logging.INFO)


class MonitoredLanguageModel(BaseLanguageModel):
    """
    A LangChain-compatible LLM wrapper that logs structured monitoring metrics.
    Supports latency, user/session context, and token usage logging.
    """
    target: Any = Field(...)
    name: str = Field(default="unnamed")
    _metric_store: MetricStore = PrivateAttr()

    def __init__(self, target: Any, name: str = "unnamed"):
        super().__init__(target=target, name=name)
        self._metric_store = get_metric_store()

    def _llm_type(self) -> str:
        return "monitoring_wrapper"

    def _log_and_store(self, result: Any, latency: float) -> Optional[Metric]:
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
