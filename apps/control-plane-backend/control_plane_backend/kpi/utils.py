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

from __future__ import annotations

from datetime import datetime


def resolve_interval(since: datetime, until: datetime) -> tuple[str, str]:
    """Return (opensearch_fixed_interval, strftime_format) for the given range.

    Thresholds mirror the frontend getPrecisionForRange() in timeAxis.ts.
    """
    diff = until - since
    diff_hours = diff.total_seconds() / 3600
    diff_days = diff_hours / 24

    if diff.total_seconds() <= 10:
        return "1s", "%H:%M:%S"
    if diff_hours < 10:
        return "1m", "%H:%M"
    if diff_days <= 3:
        return "1h", "%Y-%m-%d %H:00"
    return "1d", "%Y-%m-%d"
