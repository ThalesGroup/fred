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


from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict


class RuntimeContext(BaseModel):
    """
    Semi-typed runtime context that defines known properties while allowing arbitrary additional ones.
    """

    model_config = ConfigDict(extra="allow")

    selected_document_libraries_ids: list[str] | None = None
    selected_prompt_ids: list[str] | None = None
    selected_template_ids: list[str] | None = None
    search_policy: str | None = None


# Type alias for context provider functions
RuntimeContextProvider = Callable[[], Optional[RuntimeContext]]


def get_document_library_tags_ids(context: RuntimeContext | None) -> list[str] | None:
    """Helper to extract document library IDs from context."""
    if not context:
        return None
    return context.selected_document_libraries_ids


def get_search_policy(context: RuntimeContext | None) -> str:
    """Helper to extract search policy from context."""
    if not context:
        return "hybrid"
    return context.search_policy if context.search_policy else "hybrid"

def get_prompt_libraries_ids(context: RuntimeContext | None) -> list[str] | None:
    """Helper to extract prompt library IDs from context."""
    if not context:
        return None
    return context.selected_prompt_ids


def get_template_libraries_ids(context: RuntimeContext | None) -> list[str] | None:
    """Helper to extract template library IDs from context."""
    if not context:
        return None
    return context.selected_template_ids
