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
Registry mapping catalog `provider` keys to in-process MCP toolkits (MIGR-03.03).

Why this module exists:
- an MCP catalog server with `transport: inprocess` names a `provider`; the MCP
  runtime asks this factory to build the matching toolkit for the current agent turn
- keeping the mapping here (not in `agent_app`) lets the runtime wire a single
  factory reference at startup without hardcoding provider knowledge in the boot path

How to use it:
- pass `build_inprocess_toolkit` as `RuntimeConfig.inprocess_toolkit_factory`
"""

from __future__ import annotations

import logging
from typing import Any

from fred_runtime.integrations.kf_vector_search import (
    KF_VECTOR_SEARCH_PROVIDER,
    KfVectorSearchToolkit,
)

logger = logging.getLogger(__name__)


def build_inprocess_toolkit(provider: str | None, agent: Any) -> Any | None:
    """
    Build the in-process toolkit for `provider`, bound to the current agent turn.

    Returns None for an unknown or missing provider so the MCP runtime skips it with
    a warning rather than failing the whole agent.
    """
    if provider == KF_VECTOR_SEARCH_PROVIDER:
        return KfVectorSearchToolkit(agent=agent)
    logger.warning("[MCP] unknown inprocess provider=%s; no toolkit built.", provider)
    return None
