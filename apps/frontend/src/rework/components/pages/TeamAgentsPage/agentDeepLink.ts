// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/** Query param naming the agent whose edit form opens on arrival. */
export const AGENT_DEEP_LINK_PARAM = "agent";

/** The team's Agents page, optionally opening one agent's edit form. */
export function teamAgentsPath(teamId: string, agentInstanceId?: string): string {
  const base = `/team/${teamId}/agents`;
  return agentInstanceId
    ? `${base}?${new URLSearchParams({ [AGENT_DEEP_LINK_PARAM]: agentInstanceId }).toString()}`
    : base;
}
