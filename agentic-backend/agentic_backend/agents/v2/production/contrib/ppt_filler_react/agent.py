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
ReAct v2 assistant that fills a PowerPoint template from scoped documents.

This is the reference example for the new authoring style:
- declarative agent definition
- small Python tools in `tools/`
- prompts stored in markdown resources
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2.authoring import ReActAgent, prompt_md

from .tools import (
    extract_cv,
    extract_enjeux_besoins,
    extract_prestation_financiere,
    fill_template,
)

DEFAULT_SYSTEM_PROMPT = prompt_md(
    package="agentic_backend.agents.v2.production.ppt_filler_react",
    file_name="ppt_filler_react_system_prompt.md",
)


class PptFillerReActV2Definition(ReActAgent):
    """
    PowerPoint filler agent built with the v2 `ReActAgent` authoring facade.

    Quick edit guide:
    - extraction/generation behavior: prompt resources
    - business capabilities: `tools`
    - configurable template asset: `template_key`
    """

    agent_id: str = "ppt.filler.react.v2"
    role: str = "PowerPoint template filler"
    description: str = (
        "Extracts structured data from scoped documents and generates a filled "
        "PowerPoint deliverable for the user."
    )
    tags: tuple[str, ...] = ("powerpoint", "documents", "extraction", "react")
    tools = (
        extract_enjeux_besoins,
        extract_cv,
        extract_prestation_financiere,
        fill_template,
    )
    system_prompt_template: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        min_length=1,
    )
    template_key: str = "ppt_template.pptx"
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description=(
                "Business instructions for how the assistant should extract the "
                "three sections and generate the PowerPoint deliverable."
            ),
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="template_key",
            type="text",
            title="PowerPoint template key",
            description="Agent configuration resource key for the .pptx template file.",
            required=False,
            default="ppt_template.pptx",
            ui=UIHints(group="PowerPoint"),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Show file upload and attachment controls for this agent.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document libraries picker",
            description="Let users scope the document libraries used during extraction.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )
