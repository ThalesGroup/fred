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

import { store } from "../common/store";
import { KeyCloakService } from "../security/KeycloakService";
import { knowledgeFlowApi, ProcessDocumentsProgressResponse } from "./knowledgeFlow/knowledgeFlowOpenApi";
import { ProcessingProgress } from "../types/ProcessingProgress";

const UPLOAD_PROCESS_POLL_INTERVAL_MS = 2000;
const UPLOAD_PROCESS_POLL_TIMEOUT_MS = 30 * 60 * 1000;

export interface UploadProcessProgressSummary {
  filename: string;
  workflowId: string;
  summary: ProcessDocumentsProgressResponse;
}

async function pollUploadProcessProgress(
  workflowId: string,
  fileName: string,
  onProgressSummary?: (update: UploadProcessProgressSummary) => void,
): Promise<void> {
  const startedAt = Date.now();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  return new Promise<void>((resolve, reject) => {
    const poll = async () => {
      try {
        const progress = (await store
          .dispatch(
            knowledgeFlowApi.endpoints.getUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGet.initiate(
              { workflowId },
              { subscribe: false },
            ),
          )
          .unwrap()) as ProcessDocumentsProgressResponse;
        onProgressSummary?.({ filename: fileName, workflowId, summary: progress });
        const hasFailed = progress.documents_failed > 0;
        const hasSucceeded =
          progress.total_documents > 0 &&
          progress.documents_fully_processed + progress.documents_failed + progress.documents_missing >=
            progress.total_documents;

        if (hasSucceeded && hasFailed) {
          resolve();
          return;
        }

        if (hasSucceeded) {
          resolve();
          return;
        }

        if (Date.now() - startedAt >= UPLOAD_PROCESS_POLL_TIMEOUT_MS) {
          resolve();
          return;
        }

        timeoutId = setTimeout(poll, UPLOAD_PROCESS_POLL_INTERVAL_MS);
      } catch (e) {
        reject(e);
      }
    };

    poll();
  }).finally(() => {
    if (timeoutId) clearTimeout(timeoutId);
  });
}

/** Result for one file from the fire-and-forget /schedule-documents endpoint. */
export interface ScheduledDocumentResult {
  filename: string;
  document_uid?: string | null;
  status: string; // "success" | "failed"
  error?: string | null;
}

export interface ScheduleDocumentsResult {
  workflow_id?: string | null;
  scheduler_backend: string;
  documents: ScheduledDocumentResult[];
}

// Send hundreds of files in bounded batches so a single request never carries an
// unbounded payload, and one failing batch cannot lose the others' results.
const SCHEDULE_BATCH_SIZE = 20;

/**
 * Upload + schedule documents and return immediately (fire-and-forget).
 *
 * Unlike `streamUploadOrProcessDocument`, this does NOT hold a connection open
 * while documents are processed: the backend persists the files (so they appear
 * in the library right away) and submits the processing workflow, then returns.
 * Progress is then observed durably by polling the library (document metadata
 * stages), which survives navigating away, closing the drawer, or reloading.
 *
 * Robustness: batches are independent. If one batch fails (network/server), its
 * files are reported as failed and the remaining batches still run — partial
 * success is preserved and the function never rejects for a per-batch error.
 */
export async function scheduleDocuments(
  files: File[],
  metadata?: Record<string, any>,
): Promise<ScheduleDocumentsResult> {
  const token = KeyCloakService.GetToken();

  const batches: File[][] = [];
  for (let i = 0; i < files.length; i += SCHEDULE_BATCH_SIZE) {
    batches.push(files.slice(i, i + SCHEDULE_BATCH_SIZE));
  }

  const aggregated: ScheduleDocumentsResult = {
    workflow_id: null,
    scheduler_backend: "",
    documents: [],
  };

  for (const batch of batches) {
    try {
      const formData = new FormData();
      batch.forEach((file) => formData.append("files", file));
      formData.append("metadata_json", JSON.stringify(metadata ?? {}));

      const response = await fetch("/knowledge-flow/v1/schedule-documents", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Schedule failed: ${response.status} ${response.statusText}`);
      }

      const result = (await response.json()) as ScheduleDocumentsResult;
      aggregated.documents.push(...(result.documents ?? []));
      if (result.scheduler_backend) aggregated.scheduler_backend = result.scheduler_backend;
      if (result.workflow_id) aggregated.workflow_id = result.workflow_id;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      batch.forEach((file) => aggregated.documents.push({ filename: file.name, status: "failed", error: message }));
    }
  }

  return aggregated;
}

export async function streamUploadOrProcessDocument(
  file: File,
  mode: "upload" | "process",
  onProgress: (update: ProcessingProgress) => void,
  metadata?: Record<string, any>,
  onProgressSummary?: (update: UploadProcessProgressSummary) => void,
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

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let workflowId: string | undefined;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    let lines = buffer.split("\n");

    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const progress: ProcessingProgress = JSON.parse(line);
        if (progress.workflow_id) {
          workflowId = progress.workflow_id;
        }
        if (progress.step !== "done") {
          onProgress(progress);
        }
      } catch (e) {
        console.warn("Failed to parse progress line:", line, e);
      }
    }
  }

  if (mode === "process" && workflowId) {
    await pollUploadProcessProgress(workflowId, file.name, onProgressSummary);
  }
}
