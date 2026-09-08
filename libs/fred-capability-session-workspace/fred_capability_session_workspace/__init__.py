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

"""Fred agent capability: a session-scoped scratch filesystem shared with sub-agents."""

from fred_capability_session_workspace.capability import (
    SESSION_WORKSPACE_CAPABILITY_ID,
    SessionWorkspaceCapability,
    resolve_in_workspace,
    session_workspace_root,
)

__all__ = [
    "SESSION_WORKSPACE_CAPABILITY_ID",
    "SessionWorkspaceCapability",
    "resolve_in_workspace",
    "session_workspace_root",
]
