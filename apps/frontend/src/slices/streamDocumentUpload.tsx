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

/** FastAPI puts its explanation in `detail`; anything else is returned as-is. */
async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.text();
    if (!body) return "";
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      return typeof parsed.detail === "string" ? parsed.detail : body;
    } catch {
      return body;
    }
  } catch {
    return "";
  }
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
 * from here on), `onFileFailed` (it failed before ever getting one),
 * `onFileConflicted` (the folder gained a document of that name while the
 * import was under way, so the file still needs the user's overwrite-or-keep
 * answer — an outcome, not a failure), or `onFileResolved` (its terminal
 * `finished` line, with no task_id at all — upload-only mode, and the
 * no-scheduler process path, never emit one). It
 * fires only on that terminal line, not an earlier `success` one: the
 * no-scheduler path emits an intermediate `success` line for the upload-prep
 * step *before* actually processing the file, so treating that as done would
 * let the caller consider the file finished while it's still being processed.
 */
export async function streamUploadOrProcessDocument(
  files: File[],
  mode: "upload" | "process",
  metadata?: Record<string, any>,
  onTaskDiscovered?: (task: ScheduledTask) => void,
  onFileFailed?: (filename: string, message: string) => void,
  onFileResolved?: (filename: string) => void,
  onFileConflicted?: (filename: string) => void,
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
    // The checks that run before the stream opens — storage quota, permissions
    // — answer with an ordinary error and put their explanation in the body.
    // Dropping it left the user reading a status code for the most common
    // reason an import is refused.
    throw new Error(`Upload failed: ${response.status} ${response.statusText}. ${await errorDetail(response)}`.trim());
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
          if (event.status === "conflict") {
            // Nothing was written for this file and nothing went wrong: the
            // name was taken meanwhile and the answer is the user's to give.
            lastFailedByFilename.set(eventFilename, false);
            onFileConflicted?.(eventFilename);
          } else if (event.status === "ignored") {
            // The caller asked for this file to be skipped and it was.
            lastFailedByFilename.set(eventFilename, false);
            onFileResolved?.(eventFilename);
          } else if (event.status === "failed" || event.status === "error") {
            const message =
              typeof event.error === "string" && event.error ? event.error : `Failed to process ${eventFilename}`;
            lastFailedByFilename.set(eventFilename, true);
            firstFailureMessage ??= message;
            onFileFailed?.(eventFilename, message);
          } else if (event.status === "success" || event.status === "finished") {
            lastFailedByFilename.set(eventFilename, false);
            // Only "finished" is terminal — an earlier "success" (e.g. the
            // no-scheduler path's upload-prep step) can still be followed by
            // a real failure later in this same file's processing.
            if (event.status === "finished") onFileResolved?.(eventFilename);
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
