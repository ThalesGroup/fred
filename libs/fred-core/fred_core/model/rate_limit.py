# Copyright Thales 2026
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

"""Provider rate-limit (HTTP 429) detection, shared by every retry site."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def is_rate_limit(exc: BaseException) -> tuple[bool, float | None]:
    """Detect provider throttling and a usable Retry-After delay in seconds."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    throttled = (
        str(status) == "429"
        if status is not None
        else (
            "ratelimit" in name
            or "rate limit" in msg
            or "rate_limited" in msg
            or re.search(r"\b429\b", msg) is not None
        )
    )
    if not throttled:
        return False, None

    headers = getattr(getattr(exc, "response", None), "headers", None)
    raw = (
        (headers.get("Retry-After") or headers.get("retry-after")) if headers else None
    )
    if raw is None:
        return True, None
    try:
        delay = float(raw)
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(raw)
            if date.tzinfo is None:
                return True, None
            delay = max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return True, None
    return True, delay if math.isfinite(delay) and delay >= 0 else None
