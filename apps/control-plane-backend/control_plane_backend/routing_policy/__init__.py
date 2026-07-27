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
Team (and personal-space) LLM model routing policy (TEAM-05, #2118,
``docs/swift/rfc/TEAM-ROUTING-POLICY-RFC.md``).

Lets a team_editor (or a personal-space owner, who holds team_editor
implicitly) choose a default chat model profile and per-operation
overrides, bounded by the ``kind="model"`` capability enablement system
(#2110) rather than a separate platform-policy allowlist — see the RFC's
§7 for why that supersedes the original ``TeamPlatformPolicy.model_guardrails``
design.
"""
