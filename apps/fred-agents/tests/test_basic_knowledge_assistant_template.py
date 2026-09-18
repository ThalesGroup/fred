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
Registry and default invariants for the pre-equipped knowledge template.

Why this test exists:
- the whole point of the template is that a member creates it and it works, so
  a silently dropped default capability or a re-armed confirmation gate turns
  it back into the blank slate it exists to replace

How to use it:
- run via the default offline `fred-agents` test suite

Example:
- `pytest tests/test_basic_knowledge_assistant_template.py -q`
"""

from __future__ import annotations

from fred_agents.basic_knowledge_assistant import BASIC_KNOWLEDGE_ASSISTANT_AGENT
from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.registry import build_registry


def test_is_registered_after_the_blank_slate() -> None:
    registry = build_registry()

    assert (
        BASIC_KNOWLEDGE_ASSISTANT_AGENT.agent_id
        == "fred.github.basic-knowledge-assistant"
    )
    assert (
        registry[BASIC_KNOWLEDGE_ASSISTANT_AGENT.agent_id]
        is BASIC_KNOWLEDGE_ASSISTANT_AGENT
    )
    # The CLI picks the first entry as its default agent: the blank slate keeps
    # that role, this template is offered beside it.
    assert next(iter(registry)) == GENERAL_ASSISTANT_AGENT.agent_id


def test_defaults_cover_the_four_packs() -> None:
    declared = {ref.id for ref in BASIC_KNOWLEDGE_ASSISTANT_AGENT.default_mcp_servers}

    assert declared == {
        # team resources
        "document_access",
        "mcp-knowledge-flow-mcp-tabular",
        "document_summarize",
        "document_similarity",
        "document_verbatim",
        "document_extract",
        # team wiki
        "team_wiki",
        # Word generation
        "writable_document",
    }


def test_document_access_defaults_to_corpus_and_attachments() -> None:
    # Both packs on: the corpus stays searchable AND files can be attached.
    # `search_attachments_only` True here would silently cut the agent off from
    # the team corpus, which is half of what it exists for.
    config = BASIC_KNOWLEDGE_ASSISTANT_AGENT.default_capabilities_config[
        "document_access"
    ]

    assert config["search_attachments_only"] is False
    assert config["show_attach_files_control"] is True


def test_confirmation_gates_are_off() -> None:
    # Both capabilities ship `require_confirmation=True`. With the template's
    # exhaustive-by-default posture that would put a proceed/cancel in front of
    # the median question — see the change's design.md.
    config = BASIC_KNOWLEDGE_ASSISTANT_AGENT.default_capabilities_config

    assert config["document_extract"]["require_confirmation"] is False
    assert config["document_summarize"]["require_confirmation"] is False


def test_reasoning_is_offered_and_pre_armed() -> None:
    assert BASIC_KNOWLEDGE_ASSISTANT_AGENT.reasoning_enabled is True
    assert BASIC_KNOWLEDGE_ASSISTANT_AGENT.reasoning_default_on is True


def test_every_configured_capability_is_also_activated() -> None:
    # Configuration without activation is inert: the pod only round-trips config
    # for capabilities the instance actually selects.
    activated = {ref.id for ref in BASIC_KNOWLEDGE_ASSISTANT_AGENT.default_mcp_servers}

    assert set(BASIC_KNOWLEDGE_ASSISTANT_AGENT.default_capabilities_config) <= activated


def test_prompts_are_offered_in_both_languages_and_use_the_language_token() -> None:
    field = next(
        f for f in BASIC_KNOWLEDGE_ASSISTANT_AGENT.fields if f.key == "prompts.system"
    )
    english = field.default
    french = (field.default_by_lang or {}).get("fr")

    assert isinstance(english, str) and isinstance(french, str)
    # The runtime substitutes {response_language}; restating a language rule in
    # prose would fight a session pinned to another language.
    assert "{response_language}" in english
    assert "{response_language}" in french
