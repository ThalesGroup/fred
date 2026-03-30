"""
Private legacy runtime bridge for Python-authored v2 tools.

Audience:
- `Fred developer` only
- this file is internal v2 SDK/runtime glue
- agent authors should not read or import anything from here

Why this module exists:
- `authoring/api.py` should stay focused on the public SDK surface an agent
  author reads
- locally authored Python tools still need a small runtime adapter so they can
  call Fred capabilities such as model extraction, artifact publishing, and
  media fetches
- the media/token-refresh path still depends on legacy runtime objects today,
  so keeping it here prevents that migration tax from polluting the public API

How to use it:
- runtime-facing authoring glue imports `_AuthorRuntime`
- agent authors should not import this module directly

Example:
- `runtime = _AuthorRuntime(definition=definition, binding=binding, settings=settings, ports=ports)`
"""

from __future__ import annotations

from typing import cast

from fred_core import get_keycloak_client_id, get_keycloak_url
from langchain_core.language_models.chat_models import BaseChatModel

from agentic_backend.common.kf_markdown_media_client import KfMarkdownMediaClient
from agentic_backend.common.structures import AgentSettings
from agentic_backend.common.user_token_refresher import (
    refresh_user_access_token_from_keycloak,
)

from ..contracts.context import BoundRuntimeContext
from ..contracts.models import ReActAgentDefinition
from ..contracts.runtime import ToolInvokerPort
from ..support.authored_toolsets import AuthoredToolRuntimePorts


class _LegacyMarkdownMediaClientAdapter:
    """
    Minimal legacy adapter for `KfMarkdownMediaClient`.

    Why this exists:
    - `KfMarkdownMediaClient` still expects an old `AgentFlow`-shaped object
    - authored tools may need to fetch packaged media while the broader runtime
      migration is still in progress

    How to use it:
    - instantiate only inside `_AuthorRuntime.fetch_media(...)`

    Example:
    - `adapter = _LegacyMarkdownMediaClientAdapter(binding=binding, settings=settings)`
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self.runtime_context = binding.runtime_context
        self.agent_settings = settings

    def refresh_user_access_token(self) -> str:
        """
        Refresh the user access token for media fetches.

        Why this exists:
        - the legacy media client expects the agent object to expose token
          refresh behavior directly

        How to use it:
        - call indirectly through `KfMarkdownMediaClient`

        Example:
        - `token = shim.refresh_user_access_token()`
        """
        refresh_token = self.runtime_context.refresh_token
        if not refresh_token:
            raise RuntimeError(
                "Cannot refresh user access token: refresh_token missing from runtime context."
            )

        keycloak_url = get_keycloak_url()
        client_id = get_keycloak_client_id()
        if not keycloak_url:
            raise RuntimeError(
                "User security realm_url is not configured for Keycloak."
            )
        if not client_id:
            raise RuntimeError(
                "User security client_id is not configured for Keycloak."
            )

        payload = refresh_user_access_token_from_keycloak(
            keycloak_url=keycloak_url,
            client_id=client_id,
            refresh_token=refresh_token,
        )
        new_access_token = payload.get("access_token")
        new_refresh_token = payload.get("refresh_token") or refresh_token
        if not isinstance(new_access_token, str) or not new_access_token:
            raise RuntimeError(
                "Keycloak refresh response did not include a valid access_token."
            )
        self.runtime_context.access_token = new_access_token
        self.runtime_context.refresh_token = new_refresh_token
        return new_access_token


class _AuthorRuntime:
    """
    Small runtime bundle used by authored Python tools.

    Why this exists:
    - authored tools need one place to reach the bound model, fallback Fred
      tool invoker, artifact/resource ports, and media fetch path
    - these details are runtime glue, not part of the public authoring API

    How to use it:
    - create one instance per bound authored-tool handler set
    - inject it into `ToolContext`

    Example:
    - `runtime = _AuthorRuntime(definition=definition, binding=binding, settings=settings, ports=ports)`
    """

    def __init__(
        self,
        *,
        definition: ReActAgentDefinition,
        binding: BoundRuntimeContext,
        settings: AgentSettings,
        ports: AuthoredToolRuntimePorts,
    ) -> None:
        self.definition = definition
        self.binding = binding
        self.settings = settings
        self.ports = ports
        self._model: BaseChatModel | None = None
        self._media_client: KfMarkdownMediaClient | None = None

    @property
    def model(self) -> BaseChatModel:
        """
        Return the bound chat model for authored helper calls.

        Why this exists:
        - helpers such as structured extraction need the same model selection as
          the parent authored agent runtime

        How to use it:
        - access through `ToolContext`, not directly from authored tool code

        Example:
        - `model = runtime.model`
        """
        if self._model is None:
            if self.ports.chat_model_factory is None:
                raise RuntimeError(
                    "Authored local tools require RuntimeServices.chat_model_factory."
                )
            self._model = cast(
                BaseChatModel,
                self.ports.chat_model_factory.build(self.definition, self.binding),
            )
        return self._model

    @property
    def tool_invoker(self) -> ToolInvokerPort:
        """
        Return the fallback Fred tool invoker for authored helper calls.

        Why this exists:
        - authored tools often need Fred-native capabilities such as knowledge
          search without directly depending on runtime service objects

        How to use it:
        - access through `ToolContext.invoke_tool(...)` or
          `ToolContext.helpers...`, not directly from authored tool code

        Example:
        - `invoker = runtime.tool_invoker`
        """
        invoker = self.ports.fallback_tool_invoker
        if invoker is None:
            raise RuntimeError(
                "Authored local tools require a fallback tool invoker for Fred capabilities."
            )
        return invoker

    async def fetch_media(self, document_uid: str, file_name: str) -> bytes:
        """
        Fetch one binary media attachment referenced by packaged markdown.

        Why this exists:
        - authored tools occasionally need the same media fetch path used by the
          older markdown/media agent stack

        How to use it:
        - call through `ToolContext.fetch_media(...)`

        Example:
        - `content = await runtime.fetch_media(document_uid, "diagram.png")`
        """
        if self._media_client is None:
            from agentic_backend.core.agents.agent_flow import AgentFlow

            self._media_client = KfMarkdownMediaClient(
                agent=cast(
                    AgentFlow,
                    _LegacyMarkdownMediaClientAdapter(
                        binding=self.binding,
                        settings=self.settings,
                    ),
                )
            )
        return await self._media_client.fetch_media(document_uid, file_name)
