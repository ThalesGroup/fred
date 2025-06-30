import logging
import time
import json
from typing import Optional, Dict, Any

from fred.monitoring.tool_monitoring.tool_metric_type import ToolMetric

logger = logging.getLogger(__name__)


def translate_to_metric(
    raw: Dict[str, Any],
    ctx: Dict[str, str],
) -> Optional[ToolMetric]:
    try:
        logger.debug(f"Latency: {raw.get("latency",-1):.4f}, Tool Name: {raw.get("tool_name","unknown")}")

        metric = ToolMetric(
            timestamp=raw.get("timestamp", time.time()),
            latency=raw.get("latency",-1),
            tool_name=raw.get("tool_name","unknown"),
            user_id=ctx.get("user_id", "unknown"),
            session_id=ctx.get("session_id", "unknown"),
        )
        return metric

    except Exception as e:
        logger.warning("❌ Failed to translate metadata into Metric.")
        logger.warning(f"Exception: {e}")
        logger.warning(f"Raw input:\n{json.dumps(raw, indent=2, default=str)}")
        return None