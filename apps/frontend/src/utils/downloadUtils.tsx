// Copyright Thales 2025
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

import { KeyCloakService } from "../security/KeycloakService";

/**
 * Downloads a file by creating a temporary link and clicking it
 */
export const downloadFile = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "document";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

/**
 * Authenticated download: fetch a (session-protected) URL with the live Bearer
 * token, then save the response as a blob.
 *
 * Workspace files are proxied through Knowledge Flow and the `/fs/download` route
 * requires authentication — a plain anchor navigation carries no token and fails.
 * This is the single place that turns a protected URL into a saved file; both the
 * Resources file browser and agent-produced artifact links go through it.
 */
export const downloadAuthed = async (url: string, filename: string): Promise<void> => {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
  });
  if (!response.ok) {
    throw new Error(`Download failed (${response.status})`);
  }
  downloadFile(await response.blob(), filename);
};
