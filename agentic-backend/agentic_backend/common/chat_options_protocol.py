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
Leaf module — no internal imports — so both `agent_spec` and `kf_vector_search_params`
can import `ChatOptionsEditor` without creating a circular dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentic_backend.common.structures import AgentChatOptions


@runtime_checkable
class ChatOptionsEditor(Protocol):
    """
    Protocol for tool param models that contribute to AgentChatOptions.

    Implement `edit_chat_options` on a param model to let it opt in or out of
    specific chat UI controls based on its own field values.  The method receives
    a mutable copy of the options and modifies it in-place.  The caller is
    responsible for copying once before iterating over all editors.

    Convention: only set flags to True — do not force flags to False unless the
    param model has a deliberate reason to suppress a capability.
    """

    def edit_chat_options(self, options: AgentChatOptions) -> None: ...
