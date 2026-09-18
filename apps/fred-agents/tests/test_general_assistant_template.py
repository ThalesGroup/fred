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
Invariants for the blank-slate template every team starts from.

Why this test exists:
- "blank" is a load-bearing property, not an accident of authoring: every
  default a template declares becomes an admission hurdle a team must clear
  before an admin can enable it, and this is the one template that must suit
  any team. Pre-equipped siblings exist precisely so this one can stay empty

How to use it:
- run via the default offline `fred-agents` test suite

Example:
- `pytest tests/test_general_assistant_template.py -q`
"""

from __future__ import annotations

from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT


def test_the_blank_slate_declares_nothing() -> None:
    # If a default belongs on a ready-to-use template, add it to a pre-equipped
    # sibling (`basic_assistant`, `basic_knowledge_assistant`) — not here.
    assert GENERAL_ASSISTANT_AGENT.default_mcp_servers == ()
    assert GENERAL_ASSISTANT_AGENT.default_capabilities_config == {}
    assert GENERAL_ASSISTANT_AGENT.reasoning_enabled is False
    assert GENERAL_ASSISTANT_AGENT.reasoning_default_on is False


def test_its_name_is_offered_in_french() -> None:
    assert GENERAL_ASSISTANT_AGENT.role == "Custom assistant"
    assert (GENERAL_ASSISTANT_AGENT.role_by_lang or {})[
        "fr"
    ] == "Assistant personnalisé"
