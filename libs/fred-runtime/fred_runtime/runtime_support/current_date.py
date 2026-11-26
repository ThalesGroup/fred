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

"""Current UTC date context shared by agent model-call paths."""

from datetime import UTC, datetime


def current_date_instruction() -> str:
    date = datetime.now(UTC).date().isoformat()
    return (
        f"The current UTC date is {date}. Use this date as authoritative for the "
        "real present day if other prompt text disagrees. For an ordinary question "
        "asking today's date, answer with the date only, without a time or UTC "
        "label. A local calendar date cannot be determined from a UTC date "
        "without the current time. If asked for today's date in a named place "
        "or timezone, state that you only know the UTC date and give it; do not "
        "claim it is the local date. "
        "Follow explicitly fictional or historical date requests as given."
    )
