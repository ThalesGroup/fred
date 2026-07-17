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
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    SidePanelSpec,
)
from fred_sdk.contracts.context import ToolInvocationResult, UiPart
from fred_sdk.contracts.models import FieldSpec
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DemoEchoConfig(BaseModel):
    """The one scalar agent-creation setting of the demo capability."""

    uppercase: bool = False


# --- Tables (RFC §7.1) -----------------------------------------------------
#
# The demo capability's tables live under their OWN declarative base so their
# metadata never mixes with fred-runtime's or another capability's; migrations
# ship beside this module and apply under `cap_demo_echo_alembic_version`.


class DemoBase(DeclarativeBase):
    """Isolated declarative base for the demo capability's own tables."""


class DemoEchoNote(DemoBase):
    """
    One persisted echo note (#1979 tables tracer).

    Hygiene (RFC §7.1, enforced at pod boot):
    - name is prefixed `cap_demo_echo_` (the `cap_<id>_` convention)
    - no foreign keys — `session_id` references a core id as a PLAIN column, so
      install/uninstall ordering stays free
    """

    __tablename__ = "cap_demo_echo_notes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str] = mapped_column(String, nullable=False)
    uppercase: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# --- Router (RFC §9.1) -----------------------------------------------------
#
# Auto-mounted under `/capabilities/demo_echo` with the same bearer the pod
# validates for `/agents/*`. Typed request/response so the per-capability
# OpenAPI dump generates a fully-typed RTK Query slice.


class DemoAnalyzeRequest(BaseModel):
    """Input to the demo capability's `analyze` route."""

    text: str


class DemoAnalyzeResponse(BaseModel):
    """Result of the demo capability's `analyze` route."""

    original: str
    transformed: str
    length: int


def _build_demo_router() -> APIRouter:
    """Build the demo capability's own APIRouter (no prefix — the pod mounts it
    under `/capabilities/demo_echo`)."""

    router = APIRouter(tags=["demo_echo"])

    @router.post("/analyze", response_model=DemoAnalyzeResponse)
    async def analyze(body: DemoAnalyzeRequest) -> DemoAnalyzeResponse:
        """Echo `text` back with its uppercased form and length — the smallest
        callable-from-the-browser capability route (#1979)."""

        return DemoAnalyzeResponse(
            original=body.text,
            transformed=body.text.upper(),
            length=len(body.text),
        )

    return router


class DemoCardPart(BaseModel):
    """
    The demo capability's contributed chat part (#1977, RFC §3.6).

    Why this exists:
    - the chat-parts slice needs one known-good capability part flowing
      end-to-end: manifest declaration → `UiPart` union registration →
      generated OpenAPI/frontend types → inline card in the thread
    """

    type: Literal["demo_card"] = "demo_card"
    title: str
    body: str = ""


class _DemoEchoMiddleware(AgentMiddleware):
    """Carries the `demo_echo` tool, bound to the instance's typed config."""

    def __init__(self, ctx: CapabilityContext[DemoEchoConfig, EmptyModel]) -> None:
        super().__init__()
        config = ctx.config

        @tool(response_format="content_and_artifact")
        def demo_echo(text: str) -> tuple[str, ToolInvocationResult]:
            """Echo the given text back to the conversation."""

            content = text.upper() if config.uppercase else text
            # The artifact carries the capability's chat part; the runtime
            # merges `ui_parts` onto the tool_result/final events (#1977).
            # The cast is the reference pattern for capability parts: the
            # static `UiPart` alias is the frozen base union, while the
            # registry extends the RUNTIME union with this part at boot.
            artifact = ToolInvocationResult(
                tool_ref="demo_echo",
                ui_parts=(cast(UiPart, DemoCardPart(title="Demo echo", body=content)),),
            )
            return content, artifact

        tools: Sequence[BaseTool] = [demo_echo]
        self.tools = tools


class DemoEchoCapability(AgentCapability[DemoEchoConfig, DemoEchoConfig, EmptyModel]):
    """One static tool + one scalar config field (RFC §3, tracer for #1973)."""

    manifest = CapabilityManifest(
        id="demo_echo",
        version="0.1.0",
        name="capability.demo_echo.name",
        description="capability.demo_echo.description",
        icon="graphic_eq",
        config_fields=[
            FieldSpec(
                key="uppercase",
                type="boolean",
                title="Uppercase",
                description="Echo replies in uppercase.",
                default=False,
            )
        ],
        chat_parts=[DemoCardPart],
        # #1979 tracers: one route, one owned table, one side panel — the full
        # vertical, exercised end-to-end so #1903/#1905 build on a proven slice.
        router=_build_demo_router(),
        tables=[DemoEchoNote],
        side_panels=[SidePanelSpec(widget="demo_notes")],
    )
    ConfigModel = DemoEchoConfig

    @classmethod
    def migrations_location(cls) -> str:
        """The demo capability's own Alembic tree, applied under
        `cap_demo_echo_alembic_version` by `python -m fred_runtime migrate`."""

        return str(Path(__file__).resolve().parent / "demo_migrations")

    def middleware(
        self, ctx: CapabilityContext[DemoEchoConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_DemoEchoMiddleware(ctx)]
