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

/**
 * Streams a batch upload/process request for one or more files sharing the same
 * destination metadata — one request per batch lets the backend's ReBAC/quota
 * checks cover every file in it instead of repeating per file. Returns
 * one ScheduledTask per file the server scheduled for ingestion (task_id is
 * absent in upload-only mode and when the scheduler is disabled — `onFileFailed`
 * is what still reports a failure there, since `tasks` alone can't).
 *
 * `onTaskDiscovered`/`onFileFailed` fire per file as its own line appears in the
 * stream, not after the whole batch finishes, so callers can react (tray entry,
 * toast) without waiting on the slowest file in the batch.
 */
export async function streamUploadOrProcessDocument(
  files: File[],
  mode: "upload" | "process",
  metadata?: Record<string, any>,
  onTaskDiscovered?: (task: ScheduledTask) => void,
  onFileFailed?: (filename: string, message: string) => void,
): Promise<ScheduledTask[]> {
  const token = KeyCloakService.GetToken();
  const formData = new FormData();
  for (const file of files) {
    // A file picked out of a folder (webkitdirectory input, dropped directory)
    // uploads under its RELATIVE path as the multipart filename per the HTML spec
    // — the backend then 404s trying to write temp storage under the missing
    // subdirectories. Pin each part's filename to its leaf name explicitly.
    formData.append("files", file, file.name.split("/").pop() || file.name);
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
  // Last success/failure seen per filename that never got a task_id (upload-only
  // mode, and the no-scheduler process path, never emit one at all) — "last
  // wins" because a file can look done and then still fail later in the same
  // request (e.g. its own task_run row failed to create, then the batch's
  // scheduler submission failed too): an earlier success must not suppress that.
  const lastOutcomeByFilename = new Map<string, { failed: boolean; message?: string }>();
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
            filename: eventFilename ?? files[0]?.name ?? "",
          };
          if (eventFilename) taskFilenames.add(eventFilename);
          tasks.push(task);
          onTaskDiscovered?.(task);
        } else if ((event.status === "failed" || event.status === "error") && eventFilename) {
          // The stream's final line is a batch-level summary with no filename of
          // its own (`{step: "done", status, error}`) — every genuine per-file
          // failure already has its own named line before that, so a status
          // line with no filename carries nothing to attribute to any one file.
          const message =
            typeof event.error === "string" && event.error ? event.error : `Failed to process ${eventFilename}`;
          lastOutcomeByFilename.set(eventFilename, { failed: true, message });
        } else if ((event.status === "success" || event.status === "finished") && eventFilename) {
          lastOutcomeByFilename.set(eventFilename, { failed: false });
        }
      } catch {
        // non-JSON line — ignore
      }
    }
  }

  // Report every non-task-owned file whose last known status was a failure —
  // including when the whole batch fails, so a second/third bad file isn't
  // lost behind the one that gets thrown below.
  const unresolvedFailures: { filename: string; message: string }[] = [];
  for (const [filename, outcome] of lastOutcomeByFilename) {
    if (outcome.failed && !taskFilenames.has(filename)) {
      unresolvedFailures.push({ filename, message: outcome.message! });
    }
  }
  for (const { filename, message } of unresolvedFailures) {
    onFileFailed?.(filename, message);
  }

  // Nothing in the batch resolved — signal the total failure to the caller too.
  const anyResolved = tasks.length > 0 || Array.from(lastOutcomeByFilename.values()).some((o) => !o.failed);
  if (!anyResolved && unresolvedFailures.length > 0) {
    throw new Error(unresolvedFailures[0].message);
  }

  return tasks;
}
