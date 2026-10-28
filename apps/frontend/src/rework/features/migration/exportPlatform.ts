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

import { handlePlatformAccessResponse } from "../../../common/platformAccess";
import { KeyCloakService } from "../../../security/KeycloakService";
import { downloadFile, filenameFromDisposition } from "../../../utils/downloadUtils";

// Downloads a swift-native snapshot .zip (agents, tags, document metadata) and
// triggers a browser save. The endpoint is a plain authenticated GET, so we
// fetch the blob and create a temporary object URL rather than a bare <a href>
// (which cannot carry the Authorization header).
// Backend: GET /control-plane/v1/import-export/export (platform admin only).
export async function exportPlatform(): Promise<void> {
  const token = KeyCloakService.GetToken() ?? "";
  const response = await fetch("/control-plane/v1/import-export/export", {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
  await handlePlatformAccessResponse(response);
  if (!response.ok) {
    throw new Error(`Échec de l'export (HTTP ${response.status})`);
  }

  const blob = await response.blob();
  const filename = filenameFromDisposition(response.headers.get("Content-Disposition")) ?? "swift-snapshot.zip";

  downloadFile(blob, filename);
}
