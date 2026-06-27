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

export interface PlatformImportLaunch {
  taskId: string;
  importId: string;
}

// Uploads a kea export .zip to the control-plane migration import endpoint and
// returns the task id to follow. Progress is then streamed by the shared
// task/event infrastructure (see useTaskSseManager), exactly like ingestion.
// Backend: POST /control-plane/v1/import-export/import (MIGR-05, PLATFORM-IMPORT-RFC).
export async function launchPlatformImport(file: File, label?: string): Promise<PlatformImportLaunch> {
  const token = KeyCloakService.GetToken() ?? "";

  const form = new FormData();
  form.append("file", file);
  const trimmed = label?.trim();
  if (trimmed) form.append("label", trimmed);

  const response = await fetch("/control-plane/v1/import-export/import", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!response.ok) {
    throw new Error(`Échec du lancement de la migration (HTTP ${response.status})`);
  }

  const data = (await response.json()) as { task_id: string; import_id: string };
  return { taskId: data.task_id, importId: data.import_id };
}
