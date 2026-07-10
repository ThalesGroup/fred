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
Demo capability — the minimal in-tree tracer for the capability system
(#1973).

Why this module exists:
- every slice of the capability track (registry, product surface #1974, chat
  parts #1977) needs one known-good capability to verify against; this is it:
  ONE static tool, ONE scalar config field, nothing else
- it doubles as the smallest reference implementation a capability author can
  copy

How to use (test/in-code enablement only — no product surface yet):
- register: `registry.register(DemoEchoCapability())`, or through a
  `fred.capabilities` entry point pointing at `DemoEchoCapability`
- the `demo_echo` tool exposes ONLY its LLM argument (`text`); the
  `uppercase` config reaches it through the middleware closure (RFC §3.5)
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.models import FieldSpec


class DemoEchoConfig(BaseModel):
    """The one scalar agent-creation setting of the demo capability."""

    uppercase: bool = False


class _DemoEchoMiddleware(AgentMiddleware):
    """Carries the `demo_echo` tool, bound to the instance's typed config."""

    def __init__(self, ctx: CapabilityContext[DemoEchoConfig, EmptyModel]) -> None:
        super().__init__()
        config = ctx.config

        @tool
        def demo_echo(text: str) -> str:
            """Echo the given text back to the conversation."""

            return text.upper() if config.uppercase else text

        tools: Sequence[BaseTool] = [demo_echo]
        self.tools = tools


class DemoEchoCapability(AgentCapability[DemoEchoConfig, DemoEchoConfig, EmptyModel]):
    """One static tool + one scalar config field (RFC §3, tracer for #1973)."""

    manifest = CapabilityManifest(
        id="demo_echo",
        version="0.1.0",
        name="capability.demo_echo.name",
        description="capability.demo_echo.description",
        icon="GraphicEq",
        config_fields=[
            FieldSpec(
                key="uppercase",
                type="boolean",
                title="Uppercase",
                description="Echo replies in uppercase.",
                default=False,
            )
        ],
    )
    ConfigModel = DemoEchoConfig

    def middleware(
        self, ctx: CapabilityContext[DemoEchoConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_DemoEchoMiddleware(ctx)]
