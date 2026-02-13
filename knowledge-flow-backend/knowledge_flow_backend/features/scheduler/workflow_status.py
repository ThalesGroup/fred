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

from typing import Optional

WORKFLOW_STATUS_RUNNING = "RUNNING"
WORKFLOW_STATUS_COMPLETED = "COMPLETED"
WORKFLOW_STATUS_FAILED = "FAILED"
WORKFLOW_STATUS_CANCELED = "CANCELED"
WORKFLOW_STATUS_TERMINATED = "TERMINATED"
WORKFLOW_STATUS_TIMED_OUT = "TIMED_OUT"
WORKFLOW_STATUS_CONTINUED_AS_NEW = "CONTINUED_AS_NEW"
WORKFLOW_STATUS_UNSPECIFIED = "UNSPECIFIED"

KNOWN_WORKFLOW_STATUSES = (
    WORKFLOW_STATUS_RUNNING,
    WORKFLOW_STATUS_COMPLETED,
    WORKFLOW_STATUS_FAILED,
    WORKFLOW_STATUS_CANCELED,
    WORKFLOW_STATUS_TERMINATED,
    WORKFLOW_STATUS_TIMED_OUT,
    WORKFLOW_STATUS_CONTINUED_AS_NEW,
    WORKFLOW_STATUS_UNSPECIFIED,
)

TERMINAL_FAILURE_WORKFLOW_STATUSES = frozenset(
    {
        WORKFLOW_STATUS_FAILED,
        WORKFLOW_STATUS_CANCELED,
        WORKFLOW_STATUS_TERMINATED,
        WORKFLOW_STATUS_TIMED_OUT,
    }
)

NON_TERMINAL_WORKFLOW_STATUSES = frozenset(
    {
        WORKFLOW_STATUS_RUNNING,
        WORKFLOW_STATUS_UNSPECIFIED,
        WORKFLOW_STATUS_CONTINUED_AS_NEW,
    }
)


def normalize_workflow_status(raw_status: object) -> Optional[str]:
    if raw_status is None:
        return None

    name = getattr(raw_status, "name", None)
    if isinstance(name, str) and name:
        return name.upper()

    raw_text = str(raw_status).strip()
    if not raw_text:
        return None
    upper = raw_text.upper()

    for token in KNOWN_WORKFLOW_STATUSES:
        if token in upper:
            return token
    return upper


def is_terminal_failure_status(status: Optional[str]) -> bool:
    if status is None:
        return False
    return status in TERMINAL_FAILURE_WORKFLOW_STATUSES


def is_non_terminal_status(status: Optional[str]) -> bool:
    if status is None:
        return False
    return status in NON_TERMINAL_WORKFLOW_STATUSES
