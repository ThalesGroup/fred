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


from typing_extensions import NotRequired, TypedDict


class RuntimeContext(TypedDict, total=False):
    """
    Semi-typed runtime context that defines known properties while allowing arbitrary additional ones.
    """

    # Known context properties with proper typing
    selected_library_ids: NotRequired[list[str]]

    # This allows any other keys - Python's TypedDict with __extra__ behavior
    # Note: In practice, mypy will allow extra keys in TypedDict even without explicit declaration


def get_library_ids(context: RuntimeContext | None) -> list[str] | None:
    """Helper to extract library IDs from context."""
    if not context:
        return None
    return context.get("selected_library_ids")
