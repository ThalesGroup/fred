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

import type { AgentCopyResult, ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";

/** Duplicate is a server copy into the agent's own team under the chosen name,
 * so configuration files are recreated rather than lost. */
export function duplicateCopyArgs(source: ManagedAgentInstanceSummary, routeTeamId: string, displayName: string) {
  return {
    teamId: routeTeamId,
    agentInstanceId: source.agent_instance_id,
    agentCopyRequest: { target_team_ids: [source.team_id], display_name: displayName },
  };
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** What a duplicate lost or left to redo, or null when it carries everything. */
export function duplicateWarning(result: AgentCopyResult, t: Translate): string | null {
  const lost = (result.dropped_capabilities ?? []).map((c) => t(c.name, { defaultValue: c.id }));
  const lines = [
    ...(lost.length > 0 ? [t("rework.agentCard.duplicateDropped", { capabilities: lost.join(", ") })] : []),
    ...(result.notices ?? []).map((n) => `${t(n.capability.name, { defaultValue: n.capability.id })} : ${n.message}`),
  ];
  return lines.length > 0 ? lines.join(" · ") : null;
}
