import { getConfig } from "../common/config";
import { KeyCloakService } from "../security/KeycloakService";
import { ProcessingProgress } from "../types/ProcessingProgress";

export async function streamProcessDocument(
  file: File,
  agent_name: string,
  onProgress: (update: ProcessingProgress) => void,
): Promise<void> {
  const token = KeyCloakService.GetToken();
  const formData = new FormData();
  formData.append("files", file);
  const metadata = {
    agent_name
  };
  formData.append('metadata_json', JSON.stringify(metadata));
  const backend_url_knowledge = getConfig().backend_url_knowledge;
  if (!backend_url_knowledge) {
    throw new Error("knowledged backend URL is not defined");
  }
  console.log("Backend URL:", backend_url_knowledge);
  const response = await fetch(`${getConfig().backend_url_knowledge}/knowledge/v1/process-files`, {
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

    // Keep the last partial line in the buffer
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const progress: ProcessingProgress = JSON.parse(line);
        onProgress(progress);
      } catch (e) {
        console.warn("Failed to parse progress line:", line, e);
      }
    }
  }
}
