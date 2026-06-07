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

export async function streamUploadOrProcessDocument(
  file: File,
  mode: "upload" | "process",
  metadata?: Record<string, any>,
): Promise<void> {
  const token = KeyCloakService.GetToken();
  const formData = new FormData();
  formData.append("files", file);
  formData.append("metadata_json", JSON.stringify(metadata) || "{}");

  const endpoint =
    mode === "upload" ? "/knowledge-flow/v1/upload-documents" : "/knowledge-flow/v1/upload-process-documents";

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Upload failed: ${response.status} ${response.statusText}`);
  }

  // Drain the body so the connection is released cleanly; progress is tracked
  // via the task SSE stream (taskSlice) rather than inline callbacks.
  const reader = response.body.getReader();
  while (true) {
    const { done } = await reader.read();
    if (done) break;
  }
}
