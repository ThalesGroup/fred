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
Standalone Sentinel ReAct agent definition.

Why this module exists:
- it ports the existing Sentinel Basic ReAct business profile into a direct
  `fred-sdk` definition that a standalone pod can serve
- it avoids depending on `agentic-backend` profile-discovery code for this
  first SDK extraction exercise

How to use it:
- import `SENTINEL_AGENT` and add it to a pod registry
- keep the prompt in `prompts/basic_react_sentinel_system_prompt.md`

Example:
- `from fred_agents.sentinel.profile import SENTINEL_AGENT`
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
    FieldSpec,
    MCPServerRef,
    UIHints,
    apply_global_base_prompts,
    load_agent_prompt_markdown,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy


class SentinelReActDefinition(ReActAgentDefinition):
    """
    Monitoring-focused ReAct agent served by the standalone agents pod.

    Why this class exists:
    - it gives the new pod one real production-style agent to validate the
      public `fred-sdk` and `fred-runtime` contracts
    - it preserves the business intent of the legacy Sentinel profile while
      removing the backend-only profile layer from this first migration step

    How to use it:
    - instantiate it once and register it in the pod registry
    - extend it later if Sentinel needs additional declared tools or guardrails

    Example:
    - `definition = SentinelReActDefinition()`
    """

    agent_id: str = "fred.github.sentinel"
    role: str = "Monitoring assistant"
    description: str = (
        "Operations and monitoring assistant for OpenSearch health, diagnostics, "
        "and platform KPI review."
    )
    tags: tuple[str, ...] = ("monitoring", "react")
    system_prompt_template: str = apply_global_base_prompts(
        load_agent_prompt_markdown(
            package="fred_agents.sentinel",
            file_name="basic_react_sentinel_system_prompt.md",
        )
    )
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS, locked=True),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Override the default Sentinel monitoring instructions. "
                "Leave blank to use the built-in OpenSearch diagnostics prompt."
            ),
            required=False,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    def policy(self) -> ReActPolicy:
        """
        Return the Sentinel conversational policy for the ReAct runtime.

        Why this function exists:
        - `ReActRuntime` executes standalone pod agents through a pure
          `ReActPolicy`
        - Sentinel currently only needs its system prompt and default MCP
          servers to behave like the backend profile

        How to use it:
        - call indirectly through `ReActRuntime`; authors normally just set the
          class fields and keep this method minimal

        Example:
        - `policy = SentinelReActDefinition().policy()`
        """

        return ReActPolicy(system_prompt_template=self.system_prompt_template)


SENTINEL_AGENT = SentinelReActDefinition()
