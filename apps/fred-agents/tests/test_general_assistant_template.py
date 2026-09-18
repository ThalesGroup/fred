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
Default invariants for the blank-slate template every team starts from.

Why this test exists:
- this template's defaults are load-bearing twice over: they decide what a new
  agent can do on creation, and every id in the list raises the bar a team must
  clear before an admin can enable the template at all

How to use it:
- run via the default offline `fred-agents` test suite

Example:
- `pytest tests/test_general_assistant_template.py -q`
"""

from __future__ import annotations

from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT


def test_defaults_are_the_attachments_pack_and_nothing_else() -> None:
    # Widening this list is never free: it is the admission hurdle for the one
    # template meant to suit any team, so a new id belongs to a deliberate
    # decision rather than to a convenient import.
    declared = {ref.id for ref in GENERAL_ASSISTANT_AGENT.default_mcp_servers}

    assert declared == {"document_access", "document_summarize"}


def test_document_access_stays_scoped_to_attachments() -> None:
    # This template ships no corpus search, so widening the scope would bind a
    # tool it cannot otherwise reach. `show_attach_files_control` is what makes
    # the agent form read the attachments pack as on.
    config = GENERAL_ASSISTANT_AGENT.default_capabilities_config["document_access"]

    assert config["search_attachments_only"] is True
    assert config["show_attach_files_control"] is True


def test_reasoning_is_offered_and_pre_armed() -> None:
    assert GENERAL_ASSISTANT_AGENT.reasoning_enabled is True
    assert GENERAL_ASSISTANT_AGENT.reasoning_default_on is True


def test_every_configured_capability_is_also_activated() -> None:
    # Configuration without activation is inert: the pod only round-trips config
    # for capabilities the instance actually selects.
    activated = {ref.id for ref in GENERAL_ASSISTANT_AGENT.default_mcp_servers}

    assert set(GENERAL_ASSISTANT_AGENT.default_capabilities_config) <= activated
