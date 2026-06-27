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

import { KeyCloakService } from "../../../security/KeycloakService";

export interface TeamStats {
  team_id: string;
  name: string;
  owners: number;
  managers: number;
  members: number;
  total_members: number;
  agents: number;
  prompts: number;
}

export interface PlatformStats {
  teams: number;
  distinct_users: number;
  total_agents: number;
  total_prompts: number;
  per_team: TeamStats[];
}

// Relational overview of the current platform state (teams, members by role,
// agents, prompts). Distinct from the OpenSearch KPI dashboard.
// Backend: GET /control-plane/v1/import-export/stats (platform admin only).
export async function fetchPlatformStats(): Promise<PlatformStats> {
  const token = KeyCloakService.GetToken() ?? "";
  const response = await fetch("/control-plane/v1/import-export/stats", {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`Échec du chargement des stats (HTTP ${response.status})`);
  }
  return response.json() as Promise<PlatformStats>;
}
