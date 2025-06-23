# monitored_tool.py

import time
import logging
from typing import Any, Optional
from pydantic import Field, PrivateAttr

from langchain_core.tools import BaseTool
from fred.monitoring.logging_context import get_logging_context
from fred.monitoring.metric_util import translate_response_metadata_to_metric
from fred.monitoring.metric_store import Metric

logger = logging.getLogger(__name__)


class MonitoredTool(BaseTool):
    """
    Wrapper for LangChain-compatible tools that logs usage metrics
    (latency, input, output, error) and stores them via `MetricStore`.
    """
    tool: BaseTool = Field(...)
    name: str = Field(...)
    description: str = Field(...)

    def __init__(self, tool: BaseTool):
        super().__init__(
            tool=tool,
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            return_direct=getattr(tool, "return_direct", False),
            verbose=getattr(tool, "verbose", False),
        )

    def _log_and_store(self, result: Any, latency: float) -> Optional[Metric]:
        ctx = get_logging_context()
        raw_metadata = getattr(result, "response_metadata", {}) or {}

        metric = translate_response_metadata_to_metric(
            raw=raw_metadata,
            ctx=ctx,
            latency=round(latency, 4),
            model_type=self.name,
        )

        logger.info(f"tool name : {self.tool.name} tool latency : {latency}")

        if metric:
            logger.debug(f"[{self.name}] Metric captured: {metric}")
        else:
            logger.warning(f"[{self.name}] ⚠️ Could not extract metric from result.")
        return metric

    def _run(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            result = self.tool._run(*args, **kwargs)
            self._log_and_store(result, time.perf_counter() - start)
            return result
        except Exception as e:
            logger.exception(f"[{self.name}] Tool failed: {e}")
            raise

    async def _arun(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            if 'config' not in kwargs:
                kwargs['config'] = None
            result = await self.tool._arun(*args, **kwargs)
            self._log_and_store(result, time.perf_counter() - start)
            return result
        except Exception as e:
            logger.exception(f"[{self.name}] Tool failed (async): {e}")
            raise

    def invoke(self, input: Any, **kwargs) -> Any:
        logger.debug(f"[{self.name}] invoke called with input={input}")
        return self.tool.invoke(input, **kwargs)
