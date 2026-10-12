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

"""Input and state for the web research self-test agent."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebSelfTestInput(BaseModel):
    """Any message starts the battery; its text is never sent anywhere."""

    message: str = Field(..., min_length=1)


class WebSelfTestState(BaseModel):
    latest_user_text: str
    final_text: str | None = None
    done_reason: str | None = None
