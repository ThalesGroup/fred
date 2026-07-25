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

// KEA CUTOVER 2026 — temporary. Delete this file together with KeaMigrationPage/
// and the backend's kea_migration_api.py / kea_reconciliation.py a few weeks
// after the S3NS cutover completes.
//
// Raw fetch, not the generated mutation, for the same reason as
// launchPlatformImport.ts: multipart upload is not handled by the generated
// client. The response type is still the generated one (KeaDryRunResponse) —
// never hand-declared. Zero writes on the backend — safe to call repeatedly.
// Backend: POST /control-plane/v1/kea-migration/dry-run.

import { KeyCloakService } from "../../../security/KeycloakService";
import type { KeaDryRunResponse } from "../../../slices/controlPlane/controlPlaneOpenApi";

export async function runKeaDryRun(file: File, realmFile?: File): Promise<KeaDryRunResponse> {
  const token = KeyCloakService.GetToken() ?? "";

  const form = new FormData();
  form.append("file", file);
  if (realmFile) form.append("realm_file", realmFile);

  const response = await fetch("/control-plane/v1/kea-migration/dry-run", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Dry-run échoué (HTTP ${response.status})${detail ? `: ${detail}` : ""}`);
  }

  return (await response.json()) as KeaDryRunResponse;
}
