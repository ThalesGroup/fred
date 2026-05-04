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
ContextVar that carries the active top-level span across a single agent execution.

Set it to the `agent.stream` / `agent.invoke` span at the start of each
execution so that tool and model child spans can read it and attach themselves
as children without needing the span threaded through every call site.
"""

from __future__ import annotations

import contextvars

from fred_sdk.contracts.runtime import SpanPort

active_agent_span: contextvars.ContextVar[SpanPort | None] = contextvars.ContextVar(
    "active_agent_span", default=None
)
