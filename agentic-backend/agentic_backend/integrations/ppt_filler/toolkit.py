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

"""Inprocess toolkit factory for the ``ppt_filler`` provider.

PLACEHOLDER (PPTFILL-02 / #1831): this slice only makes the provider *resolvable and
selectable* — it registers the ``ppt_filler`` key in the inprocess toolkit factory
registry so the MCP catalog entry can be picked in the agent tool picker without breaking
anything.

The actual fill tool (whose dynamic ``args_schema`` is derived per-slide from the
persisted template schema, renders the deck, uploads it to user storage, and returns a
download ``LinkPart``) is implemented in a LATER slice (PPTFILL-05 / #1834). Until then
this factory returns no tools.
"""

from __future__ import annotations

import logging

from langchain_core.tools import BaseTool

from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext

logger = logging.getLogger(__name__)


def build_ppt_filler_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """Return the in-process LangChain tools for the PPT Filler toolkit.

    Placeholder until the fill tool lands (#1834): returns an empty list so the provider
    is selectable now without exposing a half-implemented tool.
    """
    logger.debug(
        "ppt_filler toolkit requested but the fill tool is not implemented yet "
        "(PPTFILL-05 / #1834); returning no tools."
    )
    return []
