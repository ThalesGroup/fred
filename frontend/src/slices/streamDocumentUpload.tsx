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
import { KeyCloakService } from "../security/KeycloakService";
import { ProcessingProgress } from "../types/ProcessingProgress";

export async function streamUploadOrProcessDocument(
  file: File,
  mode: "upload" | "process",
  onProgress: (update: ProcessingProgress) => void,
  metadata?: Record<string, any>,
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
    mode === "upload"
      ? "/knowledge-flow/v1/upload-documents"
      : "/knowledge-flow/v1/upload-process-documents";

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
        if (progress.step !== "done") {
          onProgress(progress);
        }
      } catch (e) {
        console.warn("Failed to parse progress line:", line, e);
      }
    }
  }
}
