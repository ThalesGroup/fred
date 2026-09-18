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
Registry and default invariants for the lightly equipped assistant.

Why this test exists:
- the template exists to be usable on creation, so a dropped default turns it
  back into the blank slate it sits beside; and its list is deliberately ONE
  pack, because every id in it is an admission hurdle for the team

How to use it:
- run via the default offline `fred-agents` test suite

Example:
- `pytest tests/test_basic_assistant_template.py -q`
"""

from __future__ import annotations

from fred_agents.basic_assistant import BASIC_ASSISTANT_AGENT
from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.registry import build_registry


def test_is_registered_after_the_blank_slate() -> None:
    registry = build_registry()

    assert BASIC_ASSISTANT_AGENT.agent_id == "fred.github.basic-assistant"
    assert registry[BASIC_ASSISTANT_AGENT.agent_id] is BASIC_ASSISTANT_AGENT
    # The CLI picks the first entry as its default agent: the blank slate keeps
    # that role, this template is offered beside it.
    assert next(iter(registry)) == GENERAL_ASSISTANT_AGENT.agent_id


def test_defaults_are_the_attachments_pack_and_nothing_else() -> None:
    # Widening this list raises what a team must already be able to use before
    # an admin can enable the template, so a new id is a deliberate decision.
    declared = {ref.id for ref in BASIC_ASSISTANT_AGENT.default_mcp_servers}

    assert declared == {"document_access", "document_summarize"}


def test_document_access_stays_scoped_to_attachments() -> None:
    # No corpus search is bound here, so widening the scope would bind a search
    # this template cannot serve. `show_attach_files_control` is what makes the
    # agent form read the attachments pack as on.
    config = BASIC_ASSISTANT_AGENT.default_capabilities_config["document_access"]

    assert config["search_attachments_only"] is True
    assert config["show_attach_files_control"] is True


def test_reasoning_is_offered_and_pre_armed() -> None:
    assert BASIC_ASSISTANT_AGENT.reasoning_enabled is True
    assert BASIC_ASSISTANT_AGENT.reasoning_default_on is True


def test_every_configured_capability_is_also_activated() -> None:
    # Configuration without activation is inert: the pod only round-trips config
    # for capabilities the instance actually selects.
    activated = {ref.id for ref in BASIC_ASSISTANT_AGENT.default_mcp_servers}

    assert set(BASIC_ASSISTANT_AGENT.default_capabilities_config) <= activated


def test_prompts_are_offered_in_both_languages_and_use_the_language_token() -> None:
    field = next(f for f in BASIC_ASSISTANT_AGENT.fields if f.key == "prompts.system")
    english = field.default
    french = (field.default_by_lang or {}).get("fr")

    assert isinstance(english, str) and isinstance(french, str)
    # The runtime substitutes {response_language}; restating a language rule in
    # prose would fight a session pinned to another language.
    assert "{response_language}" in english
    assert "{response_language}" in french


def test_its_name_is_offered_in_french() -> None:
    assert (BASIC_ASSISTANT_AGENT.role_by_lang or {})["fr"] == "Assistant basique"
