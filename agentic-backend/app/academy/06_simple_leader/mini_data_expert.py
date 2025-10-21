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


"""
DataStubExpert — tiny mock "data-connected expert".

Why this exists:
- Lets us test "do-something" flows (fetch/act) without real backends.
- Returns a deterministic mini-table so the UI path is exercised.
"""

from __future__ import annotations

from typing import Sequence

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from app.core.agents.simple_agent_flow import SimpleAgentFlow


class MiniDataExpert(SimpleAgentFlow):
    """
    Hover intent:
    - This expert simulates a tool-backed response (e.g., KPI lookup).
    - Keeps the same surface as a real tool expert for easy later swap.
    """

    async def arun(self, *, messages: Sequence[AnyMessage]) -> AIMessage:
        last_user = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
        )
        ask = last_user.content if last_user else ""

        # Hard-coded mini “result”
        content = (
            "Answer (data expert): fetched live-looking values.\n"
            f"Request: “{ask}”\n\n"
            "Result:\n"
            "- kpi: sales\n"
            "- value: 91324\n"
            "- currency: EUR"
        )
        return AIMessage(
            content=content,
            additional_kwargs={
                "fred": {
                    "expert": "data_stub",
                    "result": {"kpi": "sales", "value": 91324, "currency": "EUR"},
                }
            },
        )
