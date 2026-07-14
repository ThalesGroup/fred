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
import type { ImportLaunchResponse, TaskTarget } from "../../../slices/controlPlane/controlPlaneOpenApi";

export interface PlatformImportLaunch {
  taskId: string;
  importId: string;
}

// Must match `control_plane_backend/import_export/api.py::IMPORT_TARGET_TYPE` —
// the backend creates the task's canonical TaskTarget with this same `type`
// (AUTHZ-07 Step 3). The frontend's optimistic registration below reproduces
// it so the row never flickers between two different targets before the next
// GET /tasks / SSE event replaces it with the backend's own value.
export const IMPORT_TARGET_TYPE = "platform_import";

// Same precedence as `api.py::_import_target`: trimmed operator label → the
// uploaded file's name → a safe fallback. Kept in lockstep by hand (no shared
// contract type crosses the Python/TypeScript boundary here) — the backend
// value always wins once it arrives, this is only the optimistic placeholder.
export function buildImportTarget(importId: string, label: string, filename: string): TaskTarget {
  const trimmedLabel = label.trim();
  const trimmedFilename = filename.trim();
  return { type: IMPORT_TARGET_TYPE, id: importId, label: trimmedLabel || trimmedFilename || "Platform import" };
}

// Uploads a kea export .zip to the control-plane migration import endpoint and
// returns the task id to follow. Progress is then streamed by the shared
// task/event infrastructure (see useTaskSseManager), exactly like ingestion.
// Raw fetch (not the generated mutation) because the multipart upload is not
// handled by the generated client; the response type is still the generated one.
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

  const data = (await response.json()) as ImportLaunchResponse;
  return { taskId: data.task_id, importId: data.import_id };
}
