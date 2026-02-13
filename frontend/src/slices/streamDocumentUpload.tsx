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

import { getConfig } from "../common/config";
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
        const progress = (await store.dispatch(
          knowledgeFlowApi.endpoints.getUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGet.initiate(
            { workflowId },
            { subscribe: false },
          ),
        ).unwrap()) as ProcessDocumentsProgressResponse;
        onProgressSummary?.({ filename: fileName, workflowId, summary: progress });
        const hasFailed = progress.documents_failed > 0;
        const hasSucceeded =
          progress.total_documents > 0 &&
          progress.documents_fully_processed + progress.documents_failed + progress.documents_missing >= progress.total_documents;

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

  const backend_url_knowledge = getConfig().backend_url_knowledge;
  if (!backend_url_knowledge) {
    throw new Error("Knowledge backend URL is not defined");
  }

  const endpoint =
    mode === "upload" ? "/knowledge-flow/v1/upload-documents" : "/knowledge-flow/v1/upload-process-documents";

  const response = await fetch(`${backend_url_knowledge}${endpoint}`, {
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
