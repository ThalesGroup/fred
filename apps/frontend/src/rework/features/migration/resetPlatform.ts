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

export interface PlatformResetLaunch {
  taskId: string;
}

// Wipes all agent instances, tags, and document metadata in one atomic
// transaction. Binaries, vectors, Keycloak users, and OpenFGA tuples are
// untouched. Progress is streamed by the shared task/event infrastructure
// (see useTaskSseManager), exactly like an import.
// Backend: POST /control-plane/v1/import-export/reset (platform admin only).
export async function resetPlatform(): Promise<PlatformResetLaunch> {
  const token = KeyCloakService.GetToken() ?? "";
  const response = await fetch("/control-plane/v1/import-export/reset", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`Échec du reset (HTTP ${response.status})`);
  }
  const data = (await response.json()) as { task_id: string };
  return { taskId: data.task_id };
}
