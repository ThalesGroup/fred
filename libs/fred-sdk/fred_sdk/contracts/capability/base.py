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
`AgentCapability` — the Tier 0 abstraction for modular agent features
(#1973, RFC AGENT-CAPABILITY-RFC.md §3.2).

Why this module exists:
- one abstraction carries a feature's declaration (manifest), its save-time
  validation, its computed chat surface, and its runtime middleware stack —
  replacing the per-feature scatter the RFC measures in §1.1

How to use:
- subclass with the three generic parameters and declare `manifest` plus the
  typed models; implement `tools()` — the primary, execution-model-agnostic
  authoring surface every simple capability needs::

      class PptFillerCapability(AgentCapability[PptConfig, PptStored, PptTurn]):
          manifest = CapabilityManifest(id="ppt_filler", ...)
          ConfigModel = PptConfig
          StoredConfigModel = PptStored     # defaults to ConfigModel if omitted
          TurnOptionsModel = PptTurn        # defaults to EmptyModel if omitted

          def tools(self, ctx): ...

  `middleware()` has a default that wraps `tools()` for `create_agent()`
  (ReAct); override `middleware()` directly only for ReAct-loop-specific hooks
  a plain tool cannot express (prompt injection, model-call wrapping — see
  `McpCapability`).

- installing the package IS the registration: declare a `fred.capabilities`
  entry point pointing at the subclass (RFC §4, §7)

Contract rules (RFC §3.2, §5.3):
- returned middleware must act only on the capability's own tools and state
  channels; capabilities must be mutually order-independent
- interrupt/HITL middleware is excluded — declare `HitlSpec`s instead (§5.4)
- capability `state_schema` channels are JSON-primitive by default; typed
  (pydantic) channels opt into the checkpointer msgpack allowlist via
  `manifest.state_models` (§5.2 spike rule, #1971)
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast

from langchain.agents.middleware import AgentMiddleware
from pydantic import BaseModel

from .context import CapabilityContext, EmptyModel, SaveContext
from .hitl import HitlSpec
from .manifest import CapabilityManifest, ChatControlSpec, UploadedFile

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

ConfigT = TypeVar("ConfigT", bound=BaseModel)
StoredT = TypeVar("StoredT", bound=BaseModel)
TurnOptionsT = TypeVar("TurnOptionsT", bound=BaseModel)


class AgentCapability(ABC, Generic[ConfigT, StoredT, TurnOptionsT]):
    """
    One modular agent feature: declaration + validation + runtime middleware.

    The four typed models (RFC §3.2):
    - `ConfigModel`: what the user SENDS at agent creation (drives
      `manifest.config_fields`)
    - `StoredConfigModel`: what the platform PERSISTS after
      `validate_config` enrichment; defaults to `ConfigModel`, and a
      capability deriving state at save time declares it as a SUBCLASS of
      `ConfigModel` (RFC §3.2)
    - `TurnOptionsModel`: typed chat-time values (RFC §3.5); `EmptyModel`
      if none
    - `TeamSettingsModel`: typed per-team enablement settings (RFC §8.2);
      `EmptyModel` until Tier 3
    """

    manifest: ClassVar[CapabilityManifest]
    ConfigModel: ClassVar[type[BaseModel]]
    StoredConfigModel: ClassVar[type[BaseModel]]
    TurnOptionsModel: ClassVar[type[BaseModel]] = EmptyModel
    TeamSettingsModel: ClassVar[type[BaseModel]] = EmptyModel

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # StoredConfigModel defaults to ConfigModel (RFC §3.2). Only default it
        # when the subclass declares its own ConfigModel and no
        # StoredConfigModel is visible anywhere in the MRO.
        if (
            "ConfigModel" in cls.__dict__
            and getattr(cls, "StoredConfigModel", None) is None
        ):
            cls.StoredConfigModel = cls.__dict__["ConfigModel"]

    async def validate_config(
        self,
        config: ConfigT,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> StoredT:
        """
        Agent-save-time input → stored transform (RFC §3.2, §3.8).

        Default: validate the input against `StoredConfigModel` unchanged —
        correct for capabilities without save-time enrichment. Override to
        parse uploads, raise typed validation errors, store asset binaries
        through `ctx.services` and keep only their keys.
        """

        del uploads, ctx
        return cast(StoredT, self.StoredConfigModel.model_validate(config.model_dump()))

    def chat_controls(self, config: StoredT) -> list[ChatControlSpec]:
        """
        Computed chat-time control descriptors for one agent instance
        (RFC §3.3). Evaluated at session-prep time, never persisted (§3.7).
        List order = display order. Default: no chat controls.
        """

        del config
        return []

    def upgrade_config(self, stored: Mapping[str, Any], from_version: str) -> StoredT:
        """
        Migrate an old stored-config shape (RFC §3.9). Runs lazily at read
        time. Default: plain `StoredConfigModel` validation. A raising upgrade
        suspends the agent (`capability_config_invalid`).
        """

        del from_version
        return cast(StoredT, self.StoredConfigModel.model_validate(stored))

    def hitl_specs(self) -> Sequence[HitlSpec]:
        """
        Approval declarations for this capability's tools (RFC §5.4), merged
        into the single platform HITL gate at assembly. Default: none.
        """

        return ()

    @classmethod
    def migrations_location(cls) -> str | None:
        """
        Filesystem path to this capability's own Alembic script directory
        (RFC §7.1).

        Why this exists:
        - a capability that declares `manifest.tables` ships its own migration
          scripts, applied under a per-capability version table
          (`cap_<id>_alembic_version`) — never rebased against fred-runtime's
          tree or another capability's (RFC §7.1)
        - `python -m fred_runtime migrate` discovers installed capabilities via
          the same `fred.capabilities` entry points and, for each one that
          returns a location here, runs `alembic upgrade head` against it

        How to use:
        - return an absolute path to the package's Alembic dir (the dir holding
          `env.py` + `versions/`), typically resolved relative to `__file__`
        - return `None` (default) when the capability owns no tables
        """

        return None

    def tools(
        self, ctx: CapabilityContext[StoredT, TurnOptionsT]
    ) -> Sequence["BaseTool"]:
        """
        The runtime half, execution-model-agnostic (RFC §3.2, §5): the plain
        LangChain tools this capability's turn exposes, bound to `ctx`. This is
        the PRIMARY authoring surface — implement this, not `middleware()`,
        unless the capability needs a ReAct-loop-specific hook `middleware()`
        offers (prompt injection, model-call wrapping) that a plain tool
        cannot express.

        Default: no tools.
        """

        del ctx
        return ()

    def middleware(
        self, ctx: CapabilityContext[StoredT, TurnOptionsT]
    ) -> Sequence["AgentMiddleware"]:
        """
        The ReAct-loop-only escape hatch (RFC §3.2, §5): the LangChain
        middleware STACK carrying this capability's tools and hooks, bound to
        the turn's context. Authored list order is preserved within this
        capability's block (§5.3). Only `create_agent()` (ReAct) consumes
        this; Graph agents never see it (Invariant A).

        Default: wraps `tools()` in one generic tool-carrier middleware, which
        is correct for every capability whose only runtime need is exposing
        tools. Override directly only for hooks `tools()` cannot express (see
        `McpCapability.middleware`, a prompt-fragment-only override).
        """

        tools = self.tools(ctx)
        if not tools:
            return []
        return [ToolCarrierMiddleware(tools)]


class ToolCarrierMiddleware(AgentMiddleware):
    """
    Carries one capability's `tools()` output for `create_agent()` to bind.

    Public (not `_`-prefixed) so the runtime assembly loop
    (`fred_runtime.capabilities.assembly.build_capability_agent_block`) can
    build it directly from the SAME `tools(ctx)` call used for
    `CapabilityAgentBlock.tools`/HITL binding, instead of letting the default
    `middleware()` above call `tools(ctx)` a second, separate time (CAPAB-02)
    — one `tools()` call per capability per assembly, one set of tool
    instances shared by every consumer.
    """

    def __init__(self, tools: Sequence["BaseTool"]) -> None:
        super().__init__()
        self.tools = list(tools)
