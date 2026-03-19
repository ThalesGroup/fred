from __future__ import annotations

from agentic_backend.agents.v2.candidate.DVARiskValidatorAssistant.qa import (
    DVARiskValidatorQA,
)
from agentic_backend.core.agents.v2.catalog import definition_to_agent_settings
from agentic_backend.core.agents.v2.models import ExecutionCategory


def test_dva_qa_definition_basics() -> None:
    definition = DVARiskValidatorQA()

    assert definition.agent_id == "dva.risk_validator.qa.v2"
    assert definition.execution_category == ExecutionCategory.REACT
    assert definition.system_prompt_template

    tool_refs = {tool.tool_ref for tool in definition.tool_requirements}
    assert "knowledge.search" in tool_refs


def test_dva_qa_chat_options_enabled() -> None:
    definition = DVARiskValidatorQA()

    settings = definition_to_agent_settings(
        definition,
        class_path="agentic_backend.agents.v2.candidate.DVARiskValidatorAssistant.qa.DVARiskValidatorQA",
    )

    assert settings.chat_options.attach_files is True
    assert settings.chat_options.libraries_selection is True
    assert settings.chat_options.documents_selection is True
    assert settings.chat_options.search_rag_scoping is True


def test_dva_qa_prompt_requires_retrieval() -> None:
    definition = DVARiskValidatorQA()
    prompt = definition.system_prompt_template
    assert "knowledge.search" in prompt
    assert "Always" in prompt or "always" in prompt
