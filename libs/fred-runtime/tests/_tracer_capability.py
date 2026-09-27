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
Test-only capability exercising every surface the framework can carry.

The framework tests need one capability that declares the full vertical — tool,
router, owned table, chat part, side panel, config field — so registry
validation, agent assembly, chat-part union rebuilding, route mounting and the
OpenAPI dump each have something real to work on. A shipped capability used to
play that role, which is how a test fixture ended up with an entry point, a
migration tree and a table in production databases. This one lives in the test
tree: it is never packaged, never discovered, and owns no migrations.

Anything asserting on DISCOVERY (installed `fred.capabilities` entry points)
must not use this — register it explicitly instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from importlib.metadata import EntryPoint
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
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TRACER_CAPABILITY_ID = "tracer_echo"


class TracerEchoConfig(BaseModel):
    """One scalar agent-creation setting, enough to prove config plumbing."""

    uppercase: bool = False


class TracerBase(DeclarativeBase):
    """Isolated declarative base: a capability's metadata never mixes with
    fred-runtime's or another capability's."""


class TracerEchoNote(TracerBase):
    """One owned table, shaped to pass the hygiene rules boot enforces:
    `cap_<id>_` prefix, and no foreign keys — `session_id` references a core id
    as a plain column so install/uninstall ordering stays free."""

    __tablename__ = "cap_tracer_echo_notes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str] = mapped_column(String, nullable=False)
    uppercase: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class TracerAnalyzeRequest(BaseModel):
    """Input to the capability's `analyze` route."""

    text: str


class TracerAnalyzeResponse(BaseModel):
    """Result of the capability's `analyze` route."""

    original: str
    transformed: str
    length: int


def _build_tracer_router() -> APIRouter:
    """The capability's own router — no prefix, the pod mounts it under
    `/capabilities/{id}`. Typed in and out so the per-capability OpenAPI dump
    has real schemas to emit."""

    router = APIRouter(tags=[TRACER_CAPABILITY_ID])

    @router.post("/analyze", response_model=TracerAnalyzeResponse)
    async def analyze(body: TracerAnalyzeRequest) -> TracerAnalyzeResponse:
        """Echo `text` back with its uppercased form and length."""

        return TracerAnalyzeResponse(
            original=body.text,
            transformed=body.text.upper(),
            length=len(body.text),
        )

    return router


class TracerCardPart(BaseModel):
    """The contributed chat part: manifest declaration → `UiPart` union
    registration → generated types → inline card in the thread."""

    type: Literal["tracer_card"] = "tracer_card"
    title: str
    body: str = ""


class TracerEchoCapability(
    AgentCapability[TracerEchoConfig, TracerEchoConfig, EmptyModel]
):
    """The full vertical: one tool, one route, one owned table, one chat part,
    one side panel, one config field."""

    manifest = CapabilityManifest(
        id=TRACER_CAPABILITY_ID,
        version="0.1.0",
        name="capability.tracer_echo.name",
        description="capability.tracer_echo.description",
        icon="graphic_eq",
        config_fields=[
            FieldSpec(
                key="uppercase",
                type="boolean",
                title="capability.tracer_echo.fields.uppercase.title",
                description="capability.tracer_echo.fields.uppercase.description",
                default=False,
            )
        ],
        chat_parts=[TracerCardPart],
        router=_build_tracer_router(),
        tables=[TracerEchoNote],
        side_panels=[SidePanelSpec(widget="tracer_notes")],
    )
    ConfigModel = TracerEchoConfig

    def tools(
        self, ctx: CapabilityContext[TracerEchoConfig, EmptyModel]
    ) -> Sequence[BaseTool]:
        """The capability's only runtime contribution; the default
        `middleware()` wraps it for `create_agent()`."""

        config = ctx.config

        @tool(response_format="content_and_artifact")
        async def tracer_echo(text: str) -> tuple[str, ToolInvocationResult]:
            """Echo the given text back to the conversation."""

            content = text.upper() if config.uppercase else text
            # The cast is the reference pattern for capability parts: the static
            # `UiPart` alias is the frozen base union, while the registry
            # extends the RUNTIME union with this part at boot.
            artifact = ToolInvocationResult(
                tool_ref=TRACER_CAPABILITY_ID,
                ui_parts=(
                    cast(UiPart, TracerCardPart(title="Tracer echo", body=content)),
                ),
            )
            return content, artifact

        return [tracer_echo]


TRACER_ENTRY_POINT = EntryPoint(
    name=TRACER_CAPABILITY_ID,
    value="_tracer_capability:TracerEchoCapability",
    group="fred.capabilities",
)


def install_tracer_entry_point(monkeypatch) -> None:
    """Make this fixture discoverable exactly as an installed package is.

    `fred-runtime` declares no `fred.capabilities` entry point of its own, so
    anything testing the discovery path — router auto-mount, chat-part union
    rebuild at boot, catalog advertisement — has to supply one.
    """

    from fred_runtime.capabilities import registry as registry_module

    monkeypatch.setattr(
        registry_module,
        "_installed_entry_points",
        lambda group: [TRACER_ENTRY_POINT] if group == "fred.capabilities" else [],
    )
