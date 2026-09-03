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

from typing import Optional


def is_rate_limit(exc: BaseException) -> tuple[bool, Optional[float]]:
    """
    Report whether `exc` is a provider rate-limit, plus a `Retry-After` hint.

    Why this exists:
    - providers surface 429 in different shapes through LangChain, so this
      probes a status code, the exception type name and the message text
      rather than importing any one provider's error class
    - single-sourced so the runtime's model-call retry and Knowledge Flow's
      extraction map phase cannot drift apart on what "throttled" means

    How to use:
    - `throttled, retry_after = is_rate_limit(exc)`; `retry_after` is seconds
      and is None whenever the provider supplied no usable hint
    """

    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    throttled = (
        status == 429
        or "ratelimit" in name
        or "rate limit" in msg
        or "rate_limited" in msg
        or "429" in msg
    )

    retry_after: Optional[float] = None
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers:
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw:
            try:
                retry_after = float(raw)
            except (TypeError, ValueError):
                retry_after = None
    return throttled, retry_after
