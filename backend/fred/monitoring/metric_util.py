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

import logging
import time
import json
from typing import Optional, Union, Dict, Any

from pydantic import BaseModel

from fred.monitoring.metric_types import TokenUsage, TokenDetails
from fred.monitoring.metric_store import Metric

logger = logging.getLogger(__name__)


def flatten_numeric_fields(prefix: str, obj: Any) -> Dict[str, float]:
    flat: Dict[str, float] = {}

    if isinstance(obj, BaseModel):
        data = obj.model_dump(exclude_none=True)
    elif isinstance(obj, dict):
        data = obj
    else:
        return flat

    for k, v in data.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, (int, float)):
            flat[full_key] = float(v)
        elif isinstance(v, (dict, BaseModel)):
            flat.update(flatten_numeric_fields(full_key, v))

    return flat

def normalize_token_usage(raw_token_usage: Union[dict, TokenUsage]) -> TokenUsage:
    if isinstance(raw_token_usage, TokenUsage):
        return raw_token_usage

    if isinstance(raw_token_usage, dict):
        # Defensive copy
        usage_copy = raw_token_usage.copy()

        ct_details = usage_copy.get("completion_tokens_details")
        pt_details = usage_copy.get("prompt_tokens_details")

        if isinstance(ct_details, dict):
            usage_copy["completion_tokens_details"] = TokenDetails(**ct_details)

        if isinstance(pt_details, dict):
            usage_copy["prompt_tokens_details"] = TokenDetails(**pt_details)

        return TokenUsage(**usage_copy)

    raise TypeError(f"token_usage must be a dict or TokenUsage instance, got {type(raw_token_usage)}")


def translate_response_metadata_to_metric(
    raw: Dict[str, Any],
    ctx: Dict[str, str],
    latency: float,
    model_type: str
) -> Optional[Metric]:
    try:
        logger.info(f"Raw metadata: {json.dumps(raw, indent=2, default=str)}")
        logger.info(f"Logging context: {ctx}")
        logger.info(f"Latency: {latency:.4f}, Model Type: {model_type}")

        token_usage_raw = raw.get("token_usage")
        token_usage = normalize_token_usage(token_usage_raw) if token_usage_raw else None

        metric = Metric(
            timestamp=raw.get("timestamp", time.time()),
            latency=latency,
            user_id=ctx.get("user_id", "unknown"),
            session_id=ctx.get("session_id", "unknown"),
            model_type=model_type,
            finish_reason=raw.get("finish_reason"),
            model_name=raw.get("model_name"),
            system_fingerprint=raw.get("system_fingerprint"),
            service_tier=raw.get("service_tier"),
            token_usage=token_usage.model_dump() if token_usage else None,  # ✅ KEY FIX
        )

        return metric

    except Exception as e:
        logger.warning("❌ Failed to translate metadata into Metric.")
        logger.warning(f"Exception: {e}")
        logger.warning(f"Raw input:\n{json.dumps(raw, indent=2, default=str)}")
        return None
