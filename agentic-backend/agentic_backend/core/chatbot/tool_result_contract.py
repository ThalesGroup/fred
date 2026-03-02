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

from __future__ import annotations

import json
from typing import Any, Optional


def coerce_latency_ms(raw: Any) -> Optional[int]:
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(float(raw))
        except ValueError:
            return None
    return None


def _format_latency_ms_short(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    if ms < 10000:
        return f"{ms / 1000:.1f}s"
    return f"{round(ms / 1000)}s"


def _normalize_extras(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _build_summary(
    *,
    ok: bool,
    source_count: int,
    latency_ms: Optional[int],
    explicit_summary: Optional[str],
) -> str:
    if explicit_summary:
        return explicit_summary

    if source_count > 0:
        base = f"{source_count} result{'s' if source_count != 1 else ''}"
    else:
        base = "Completed" if ok else "Failed"

    if latency_ms is not None:
        return f"{base} in {_format_latency_ms_short(latency_ms)}"
    return base


def _infer_ok_flag(raw_metadata: dict[str, Any], content: str) -> Optional[bool]:
    if isinstance(raw_metadata, dict):
        explicit_ok = raw_metadata.get("ok")
        if isinstance(explicit_ok, bool):
            return explicit_ok

        success = raw_metadata.get("success")
        if isinstance(success, bool):
            return success

        status = raw_metadata.get("status")
        if isinstance(status, str):
            status_lc = status.lower()
            if status_lc in ("ok", "success", "succeeded", "completed"):
                return True
            if status_lc in ("error", "failed", "fail", "exception"):
                return False

        if raw_metadata.get("error") or raw_metadata.get("is_error") is True:
            return False
        if raw_metadata.get("failed") is True:
            return False

    stripped = content.strip()
    lowered = stripped.lower()
    if lowered.startswith("error") or lowered.startswith("exception"):
        return False
    if "toolexception" in lowered or "traceback" in lowered:
        return False

    try:
        parsed = json.loads(stripped)
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        parsed_ok = parsed.get("ok")
        if isinstance(parsed_ok, bool):
            return parsed_ok

        parsed_success = parsed.get("success")
        if isinstance(parsed_success, bool):
            return parsed_success

        parsed_status = parsed.get("status")
        if isinstance(parsed_status, str):
            status_lc = parsed_status.lower()
            if status_lc in (
                "ok",
                "success",
                "succeeded",
                "completed",
                "green",
                "healthy",
                "up",
            ):
                return True
            if status_lc in (
                "error",
                "failed",
                "fail",
                "exception",
                "red",
                "unhealthy",
                "down",
            ):
                return False

        if parsed.get("error") or parsed.get("is_error") is True:
            return False

    return None


def normalize_tool_result_contract(
    *,
    raw_metadata: dict[str, Any],
    content: str,
    source_count: int,
) -> tuple[bool, Optional[int], dict[str, Any]]:
    """
    Canonicalize tool-result telemetry for UI rendering.
    Returns:
      - ok flag (always boolean),
      - latency in ms (optional),
      - normalized extras containing a concise `summary`.
    """
    latency_ms = coerce_latency_ms(raw_metadata.get("latency_ms"))
    inferred_ok = _infer_ok_flag(raw_metadata, content)
    ok_flag = inferred_ok if isinstance(inferred_ok, bool) else True

    extras = _normalize_extras(raw_metadata.get("extras"))
    explicit_summary = extras.get("summary")
    if not isinstance(explicit_summary, str) or not explicit_summary.strip():
        explicit_summary = None

    extras["summary"] = _build_summary(
        ok=ok_flag,
        source_count=source_count,
        latency_ms=latency_ms,
        explicit_summary=explicit_summary,
    )
    return ok_flag, latency_ms, extras
