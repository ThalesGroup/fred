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

from __future__ import annotations

from inspect import signature
from typing import get_type_hints

from fred_sdk.contracts.runtime import ConversationScratchpadPort, RuntimeServices


def test_runtime_services_exposes_only_conversation_bound_scratchpad_operations() -> None:
    method_names = {
        "read_text",
        "write_text",
        "edit_text",
        "list",
        "exists",
        "delete",
    }

    assert get_type_hints(RuntimeServices)["conversation_scratchpad"] == (
        ConversationScratchpadPort | None
    )
    assert method_names <= set(ConversationScratchpadPort.__abstractmethods__)
    for method_name in method_names:
        parameters = signature(getattr(ConversationScratchpadPort, method_name)).parameters
        assert "session_id" not in parameters
        assert "namespace" not in parameters
        assert "bucket" not in parameters
