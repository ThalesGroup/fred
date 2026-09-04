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
  filename: string;
}

// A file picked out of a folder (webkitdirectory input, dropped directory)
// carries its RELATIVE path in File.name — the backend echoes back (and expects
// multipart parts named as) the leaf only. Both directions of that convention
// share this helper.
export function leafFileName(file: File): string {
  return file.name.split("/").pop() || file.name;
}

/**
 * Streams a batch upload/process request for one or more files sharing the same
 * destination metadata — one request per batch lets the backend's ReBAC/quota
 * checks cover every file in it instead of repeating per file. Returns one
 * ScheduledTask per file the server scheduled for ingestion.
 *
 * Every file gets exactly one outcome callback, fired the moment its own line
 * appears in the stream (not after the whole batch finishes): `onTaskDiscovered`
 * (it got a task_id — the tray/Activity owns any later failure for that task
 * from here on), `onFileFailed` (it failed before ever getting one), or
 * `onFileResolved` (a plain success/finished line with no task_id at all —
 * upload-only mode, and the no-scheduler process path, never emit one). A file
 * can still fail *after* `onFileResolved` — that later failure still fires
 * `onFileFailed` when its line arrives.
 */
export async function streamUploadOrProcessDocument(
  files: File[],
  mode: "upload" | "process",
  metadata?: Record<string, any>,
  onTaskDiscovered?: (task: ScheduledTask) => void,
  onFileFailed?: (filename: string, message: string) => void,
  onFileResolved?: (filename: string) => void,
): Promise<ScheduledTask[]> {
  const token = KeyCloakService.GetToken();
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file, leafFileName(file));
  }
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
  const seenTaskIds = new Set<string>();
  // Filenames that got a task_id at some point — any later failure for one of
  // these is that task's own failure to report, via the tray/Activity, forever
  // exempt from onFileFailed regardless of event order.
  const taskFilenames = new Set<string>();
  // Last known failed/not per filename that never got a task_id — used only for
  // the final "did anything in the batch actually succeed" decision below, since
  // a later failure augments rather than invalidates an earlier success signal.
  const lastFailedByFilename = new Map<string, boolean>();
  let firstFailureMessage: string | null = null;
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
        const eventFilename = typeof event.filename === "string" && event.filename ? event.filename : undefined;
        if (typeof event.task_id === "string" && event.task_id && !seenTaskIds.has(event.task_id)) {
          seenTaskIds.add(event.task_id);
          const task: ScheduledTask = {
            taskId: event.task_id,
            documentUid: typeof event.document_uid === "string" && event.document_uid ? event.document_uid : null,
            filename: eventFilename ?? "",
          };
          if (eventFilename) taskFilenames.add(eventFilename);
          tasks.push(task);
          onTaskDiscovered?.(task);
        } else if (eventFilename && !taskFilenames.has(eventFilename)) {
          // The stream's final line is a batch-level summary with no filename of
          // its own (`{step: "done", status, error}`) — every genuine per-file
          // outcome already has its own named line before that, so a status line
          // with no filename carries nothing to attribute to any one file.
          if (event.status === "failed" || event.status === "error") {
            const message =
              typeof event.error === "string" && event.error ? event.error : `Failed to process ${eventFilename}`;
            lastFailedByFilename.set(eventFilename, true);
            firstFailureMessage ??= message;
            onFileFailed?.(eventFilename, message);
          } else if (event.status === "success" || event.status === "finished") {
            lastFailedByFilename.set(eventFilename, false);
            onFileResolved?.(eventFilename);
          }
        }
      } catch {
        // non-JSON line — ignore
      }
    }
  }

  // Nothing in the batch actually resolved — signal the total failure too.
  const anyResolved = tasks.length > 0 || Array.from(lastFailedByFilename.values()).some((failed) => !failed);
  if (!anyResolved && firstFailureMessage) {
    throw new Error(firstFailureMessage);
  }

  return tasks;
}
