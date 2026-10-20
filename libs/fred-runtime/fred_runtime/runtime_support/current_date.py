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

"""Current calendar date supplied to model calls across execution models."""

from datetime import UTC, datetime

DEFERRED_TODAY_TOKEN = "[[fred-runtime-today]]"


def current_utc_date() -> str:
    return datetime.now(tz=UTC).date().isoformat()


def current_date_instruction(today: str | None = None) -> str:
    today = today or current_utc_date()
    return (
        f"Current UTC date: {today}. "
        "When asked for today's date, give the date without a time."
    )


def add_current_date_to_system_prompt(prompt: str) -> str:
    today = current_utc_date()
    instruction = current_date_instruction(today)
    prompt = prompt.replace(DEFERRED_TODAY_TOKEN, today)
    closing_tag = "</platform_instructions>"
    if closing_tag in prompt:
        return prompt.replace(closing_tag, f"{instruction}\n{closing_tag}", 1)
    date_block = f"<platform_instructions>\n{instruction}\n</platform_instructions>"
    return f"{date_block}\n\n{prompt}" if prompt else date_block
