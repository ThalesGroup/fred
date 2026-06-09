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
Small resource-loading helpers used by v2 agent authors.

Why this package exists:
- prompt files and other packaged text resources are part of the author-facing
  SDK surface
- grouping them here keeps author utilities separate from runtime internals

How to use it:
- import `load_packaged_markdown(...)` when an agent module wants to load a
  packaged `.md` file by explicit path
- import `load_agent_prompt_markdown(...)` when an authored agent wants the
  conventional `prompts/<file>` lookup

Example:
- `system_prompt = load_packaged_markdown(package=\"my_pkg\", path_parts=(\"prompts\", \"system.md\"))`
"""

from .prompts import load_agent_prompt_markdown, load_packaged_markdown

__all__ = [
    "load_agent_prompt_markdown",
    "load_packaged_markdown",
]
