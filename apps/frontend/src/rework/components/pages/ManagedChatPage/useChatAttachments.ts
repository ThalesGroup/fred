// Copyright Thales 2026
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

import { useCallback, useMemo, useState } from "react";
import { useDispatch } from "react-redux";
import { v4 as uuidv4 } from "uuid";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { streamUploadOrProcessDocument } from "../../../../slices/streamDocumentUpload";
import { taskEventReceived, taskRegistered } from "../../../features/tasks/taskSlice";
import type { ChatAttachment, ChatImageContext } from "@rework/types/attachments";

const USER_STORAGE_UPLOAD_URL = "/knowledge-flow/v1/storage/user/upload";
const FAST_INGEST_URL = "/knowledge-flow/v1/fast/ingest";
const UPLOAD_PREFIX = "uploads";
const MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024;
const ALLOWED_INLINE_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

interface UserStorageUploadResponse {
  key?: string;
  file_name?: string;
  size?: number;
  download_url?: string;
}

interface UserStorageUploadResult extends UserStorageUploadResponse {
  requestedKey: string;
}

interface FastIngestResponse {
  document_uid?: string;
}

function emitLocalTaskEvent(
  dispatch: ReturnType<typeof useDispatch>,
  taskId: string,
  state: "running" | "succeeded" | "failed",
  target: { type: string; id: string; label: string } | null,
  step: string | null,
  error: string | null = null,
) {
  dispatch(
    taskEventReceived({
      kind: "ingestion",
      task_id: taskId,
      state,
      seq: state === "running" ? 0 : 1,
      timestamp: new Date().toISOString(),
      progress: state === "succeeded" ? 100 : state === "failed" ? null : 10,
      step,
      error,
      target,
      owner: null,
      detail: null,
    }),
  );
}

function safeUploadKey(file: File): string {
  const cleaned = file.name.replace(/[^\w.\-]+/g, "_").replace(/^_+/, "") || "file";
  return `${UPLOAD_PREFIX}/${Date.now()}-${cleaned}`;
}

function workspacePath(key: string): string {
  return `/workspace/${key}`;
}

async function uploadUserFile(file: File): Promise<UserStorageUploadResult> {
  await KeyCloakService.ensureFreshToken(30);
  const token = KeyCloakService.GetToken() ?? "";
  const formData = new FormData();
  const key = safeUploadKey(file);
  formData.append("key", key);
  formData.append("file", file);

  const response = await fetch(USER_STORAGE_UPLOAD_URL, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(detail || `Upload failed (${response.status})`);
  }

  const payload = (await response.json()) as UserStorageUploadResponse;
  return { ...payload, requestedKey: key };
}

async function fastIngestAttachment(
  file: File,
  sessionId: string | null | undefined,
): Promise<FastIngestResponse | null> {
  if (!sessionId) return null;

  await KeyCloakService.ensureFreshToken(30);
  const token = KeyCloakService.GetToken() ?? "";
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);
  formData.append("scope", "session");
  formData.append("options_json", JSON.stringify({ include_summary: false }));

  const response = await fetch(FAST_INGEST_URL, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(detail || `Fast ingest failed (${response.status})`);
  }

  return (await response.json()) as FastIngestResponse;
}

function readImageContext(file: File): Promise<ChatImageContext | undefined> {
  if (!ALLOWED_INLINE_IMAGE_TYPES.has(file.type) || file.size > MAX_INLINE_IMAGE_BYTES) {
    return Promise.resolve(undefined);
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : "";
      resolve(dataUrl ? { name: file.name, mime: file.type, size: file.size, dataUrl } : undefined);
    };
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function buildAttachmentsMarkdown(attachments: ChatAttachment[]): string | null {
  const ready = attachments.filter((attachment) => attachment.status !== "error");
  if (ready.length === 0) return null;

  const lines = ["## Attached files for this turn"];
  for (const attachment of ready) {
    if (attachment.workspacePath) {
      lines.push(`- ${attachment.name}: ${attachment.workspacePath}`);
    }
    if (attachment.imageContext) {
      lines.push(
        `- ${attachment.name}: inline image (${attachment.imageContext.mime}, ${attachment.imageContext.size} bytes)`,
        `  data: ${attachment.imageContext.dataUrl}`,
      );
    }
  }
  return lines.join("\n");
}

export function useChatAttachments(sessionId: string | null) {
  const dispatch = useDispatch();
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);

  const addFiles = useCallback(
    async (files: File[], source: "picker" | "drop", activeSessionId?: string | null) => {
      const uniqueFiles = files.filter((file) => file.size > 0);
      const ingestionSessionId = activeSessionId ?? sessionId;
      for (const file of uniqueFiles) {
        const id = uuidv4();
        const localTaskId = `chat-attachment-${id}`;
        const isImage = file.type.startsWith("image/");
        dispatch(
          taskRegistered({
            taskId: localTaskId,
            kind: "ingestion",
            target: { type: "attachment", id, label: file.name },
          }),
        );
        emitLocalTaskEvent(
          dispatch,
          localTaskId,
          "running",
          { type: "attachment", id, label: file.name },
          source === "drop" ? "Préparation du traitement" : "Traitement rapide",
        );
        setAttachments((prev) => [
          ...prev,
          {
            id,
            name: file.name,
            size: file.size,
            mime: file.type,
            status: "ingesting",
            isImage,
            taskIds: [localTaskId],
          },
        ]);

        try {
          const [upload, imageContext, fastIngest] = await Promise.all([
            uploadUserFile(file),
            readImageContext(file),
            fastIngestAttachment(file, ingestionSessionId),
          ]);
          const key = upload.key ?? upload.requestedKey;
          const scheduled =
            source === "drop"
              ? await streamUploadOrProcessDocument(file, "process", { session_id: ingestionSessionId })
              : [];

          emitLocalTaskEvent(
            dispatch,
            localTaskId,
            "succeeded",
            {
              type: fastIngest?.document_uid || scheduled[0]?.documentUid ? "document" : "attachment",
              id: fastIngest?.document_uid ?? scheduled[0]?.documentUid ?? id,
              label: file.name,
            },
            "Terminé",
          );

          for (const { taskId, documentUid } of scheduled) {
            dispatch(
              taskRegistered({
                taskId,
                kind: "ingestion",
                target: documentUid ? { type: "document", id: documentUid, label: file.name } : null,
              }),
            );
          }

          setAttachments((prev) =>
            prev.map((attachment) =>
              attachment.id === id
                ? {
                    ...attachment,
                    status: "ready",
                    workspacePath: workspacePath(key),
                    imageContext,
                    documentUid: fastIngest?.document_uid,
                    taskIds: scheduled.length > 0 ? scheduled.map((task) => task.taskId) : [localTaskId],
                  }
                : attachment,
            ),
          );
        } catch (err) {
          emitLocalTaskEvent(
            dispatch,
            localTaskId,
            "failed",
            { type: "attachment", id, label: file.name },
            "Échec",
            err instanceof Error ? err.message : String(err),
          );
          setAttachments((prev) =>
            prev.map((attachment) =>
              attachment.id === id
                ? { ...attachment, status: "error", error: err instanceof Error ? err.message : String(err) }
                : attachment,
            ),
          );
        }
      }
    },
    [dispatch, sessionId],
  );

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((attachment) => attachment.id !== id));
  }, []);

  const clearReadyAttachments = useCallback(() => {
    setAttachments((prev) =>
      prev.filter((attachment) => attachment.status === "uploading" || attachment.status === "ingesting"),
    );
  }, []);

  const attachmentsMarkdown = useMemo(() => buildAttachmentsMarkdown(attachments), [attachments]);

  return {
    attachments,
    attachmentsMarkdown,
    addFiles,
    removeAttachment,
    clearReadyAttachments,
  };
}
