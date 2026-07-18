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

"""
Shared emission primitive for the security/audit logger.

Why this exists:
- Every audit-worthy event (an authorization decision, a tool invocation) needs
  to land as one structured line on `AUDIT_LOGGER_NAME`, formatted the same way,
  so a downstream log pipeline can select the whole family on one field.
- Application layers may additionally keep their own short-lived view (e.g. an
  in-memory ring buffer backing an admin UI) — that is layered on top of this,
  not a replacement for it. This function only ever writes the log line.

How to use it:
- call with a stable `event_name` (e.g. "agent.tool.invocation.completed") and
  whatever identifying/correlation fields are available; omit fields that are
  not, never fabricate them.
- never pass tool arguments, tool results, prompts, documents, tokens, or any
  other secret — this channel is audit-grade and is expected to be routed to
  long-retention storage.
"""

from __future__ import annotations

import logging

from fred_core.logs.log_setup import AUDIT_LOGGER_NAME


def emit_audit_log(
    event_name: str,
    level: str = "info",
    /,
    **fields: object,
) -> None:
    """Write one structured line to the shared security/audit logger.

    `event_name` and `level` are positional-only so that spreading a caller's
    dims dict via `**fields` (see ContextAwareTool._emit_tool_call_audit) can
    never collide with — or be mistaken by a type checker for — these two
    fixed parameters.

    `fields` becomes the JSON payload's `extra` object once CompactJsonFormatter
    formats the record (see log_setup.py). `None` values are dropped rather than
    serialized, so a caller can pass every optional field unconditionally.
    """
    payload: dict[str, object] = {"audit_event": event_name}
    payload.update({k: v for k, v in fields.items() if v is not None})
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    log_fn = getattr(logger, level)
    log_fn("[SECURITY] %s", event_name, extra=payload)


__all__ = ["emit_audit_log", "AUDIT_LOGGER_NAME"]
