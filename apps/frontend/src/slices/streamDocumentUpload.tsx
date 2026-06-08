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

export interface ScheduledTask {
  taskId: string;
  documentUid: string | null;
}

/**
 * Streams a document upload or process request, parses the ndjson response,
 * and returns one ScheduledTask per file the server scheduled for ingestion.
 * documentUid is present on the same NDJSON line as task_id (backend emits both together).
 * Returns an empty array for upload-only mode or when the scheduler is disabled.
 */
export async function streamUploadOrProcessDocument(
  file: File,
  mode: "upload" | "process",
  metadata?: Record<string, any>,
): Promise<ScheduledTask[]> {
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

  const tasks: ScheduledTask[] = [];
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const event = JSON.parse(trimmed) as Record<string, unknown>;
        if (typeof event.task_id === "string" && event.task_id) {
          tasks.push({
            taskId: event.task_id,
            documentUid: typeof event.document_uid === "string" && event.document_uid ? event.document_uid : null,
          });
        }
      } catch {
        // non-JSON line — ignore
      }
    }
  }

  return tasks;
}
