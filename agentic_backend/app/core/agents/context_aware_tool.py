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

import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import Field

from app.core.agents.runtime_context import RuntimeContextProvider, get_library_ids

logger = logging.getLogger(__name__)


class ContextAwareTool(BaseTool):
    """
    Generic wrapper tool that injects runtime context into tool calls.

    This tool acts as a proxy for any base tool, automatically injecting
    runtime context parameters when appropriate. It's designed to be extensible
    for different types of context injection.

    Current supported context injections:
    - Library IDs as 'tags' parameter for filtering operations

    Future extensions could include:
    - User preferences, session data, security contexts, etc.
    """

    base_tool: BaseTool = Field(..., description="The underlying tool to wrap")
    context_provider: RuntimeContextProvider = Field(
        ..., description="Function that provides runtime context"
    )

    def __init__(self, base_tool: BaseTool, context_provider: RuntimeContextProvider):
        super().__init__(
            **base_tool.__dict__,
            base_tool=base_tool,
            context_provider=context_provider,
        )

    def _inject_context_if_needed(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Generic method to inject runtime context into tool arguments.

        This method checks the tool's schema and conditionally injects
        context parameters that the tool supports.
        """
        context = self.context_provider()
        if not context:
            return kwargs

        tool_properties = {}
        if self.base_tool.args_schema:
            try:
                # Get schema - args_schema should be a Pydantic model class
                schema_method = getattr(
                    self.base_tool.args_schema, "model_json_schema", None
                )
                if schema_method:
                    tool_schema = schema_method()
                else:
                    schema_method = getattr(self.base_tool.args_schema, "schema", None)
                    if schema_method:
                        tool_schema = schema_method()
                    else:
                        # Fallback: assume it's already a dict-like schema
                        tool_schema = self.base_tool.args_schema

                if isinstance(tool_schema, dict):
                    tool_properties = tool_schema.get("properties", {})
            except Exception as e:
                logger.warning(f"Could not extract tool schema: {e}")
                tool_properties = {}

        # Inject library IDs as tags for filtering
        library_ids = get_library_ids(context)
        if (
            library_ids
            and "tags" in tool_properties
            and ("tags" not in kwargs or kwargs["tags"] is None)
        ):
            kwargs["tags"] = library_ids
            logger.info(f"ContextAwareTool injecting library filter: {library_ids}")

        # Future: Add other context injections here
        # Example:
        # if ("user_id" in tool_properties and
        #     "user_id" not in kwargs and
        #     hasattr(context, 'user_id')):
        #     kwargs["user_id"] = context.user_id

        return kwargs

    def _run(self, **kwargs: Any) -> Any:
        """Synchronous execution with context injection"""
        kwargs = self._inject_context_if_needed(kwargs)
        return self.base_tool._run(**kwargs)

    async def _arun(self, config=None, **kwargs: Any) -> Any:
        """Asynchronous execution with context injection"""
        kwargs = self._inject_context_if_needed(kwargs)
        return await self.base_tool._arun(config=config, **kwargs)
