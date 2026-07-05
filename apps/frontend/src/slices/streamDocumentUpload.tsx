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
 *
 * The same task_id appears on several progress lines (preparation, queued,
 * processing); each task is reported exactly once — on its first sighting — both
 * via the returned array and via the optional `onTaskDiscovered` callback. The
 * callback lets the caller register a task the instant it is known (the first
 * line of the stream) instead of waiting for the whole upload to finish, so the
 * tray/row lights up and its SSE subscription starts while the upload is still
 * streaming.
 */
export async function streamUploadOrProcessDocument(
  file: File,
  mode: "upload" | "process",
  metadata?: Record<string, any>,
  onTaskDiscovered?: (task: ScheduledTask) => void,
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
  const seen = new Set<string>();
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
        if (typeof event.task_id === "string" && event.task_id && !seen.has(event.task_id)) {
          seen.add(event.task_id);
          const task: ScheduledTask = {
            taskId: event.task_id,
            documentUid: typeof event.document_uid === "string" && event.document_uid ? event.document_uid : null,
          };
          tasks.push(task);
          onTaskDiscovered?.(task);
        }
      } catch {
        // non-JSON line — ignore
      }
    }
  }

  return tasks;
}
