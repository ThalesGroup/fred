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
"""Georges starting profile."""

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

GEORGES_PROFILE = ReActProfile(
    profile_id="georges",
    title="Georges",
    description="Friendly broad generalist assistant for fallback and open-ended queries.",
    role="Broad and general knowledge assistant",
    agent_description=(
        "Fallback generalist expert used to handle broad queries when no "
        "specialist applies."
    ),
    tags=("fallback", "generalist", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_georges_system_prompt.md"
    ),
)
