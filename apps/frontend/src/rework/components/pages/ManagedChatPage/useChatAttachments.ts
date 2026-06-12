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
import {
  useFastIngestKnowledgeFlowV1FastIngestPostMutation,
  useUploadUserFileKnowledgeFlowV1StorageUserUploadPostMutation,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation,
  useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery,
  usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { taskEventReceived, taskRegistered } from "../../../features/tasks/taskSlice";
import type { ChatAttachment, ChatImageContext, SessionAttachment } from "@rework/types/attachments";

const UPLOAD_PREFIX = "uploads";
const MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024;
const ALLOWED_INLINE_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

interface UserStorageUploadResponse {
  key?: string;
  file_name?: string;
  size?: number;
}

interface UserStorageUploadResult extends UserStorageUploadResponse {
  requestedKey: string;
}

interface FastIngestResponse {
  document_uid?: string;
  summary_md?: string;
}

interface SessionAttachmentApiPayload {
  attachment_id?: string;
  name?: string;
  mime?: string | null;
  size_bytes?: number | null;
  summary_md?: string;
  document_uid?: string | null;
  storage_key?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
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

function toSessionAttachment(payload: SessionAttachmentApiPayload): SessionAttachment {
  return {
    attachmentId: payload.attachment_id ?? "",
    name: payload.name ?? "Attachment",
    mime: payload.mime ?? undefined,
    sizeBytes: payload.size_bytes ?? undefined,
    summaryMd: payload.summary_md ?? "",
    documentUid: payload.document_uid ?? undefined,
    storageKey: payload.storage_key ?? undefined,
    workspacePath: payload.storage_key ? workspacePath(payload.storage_key) : undefined,
    createdAt: payload.created_at ?? undefined,
    updatedAt: payload.updated_at ?? undefined,
  };
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

function buildAttachmentsMarkdown(persisted: SessionAttachment[], transient: ChatAttachment[]): string | null {
  const persistedLines = persisted.flatMap((attachment) =>
    attachment.workspacePath ? [`- ${attachment.name}: ${attachment.workspacePath}`] : [],
  );
  const inlineImageLines = transient.flatMap((attachment) =>
    attachment.imageContext
      ? [
          `- ${attachment.name}: inline image (${attachment.imageContext.mime}, ${attachment.imageContext.size} bytes)`,
          `  data: ${attachment.imageContext.dataUrl}`,
        ]
      : [],
  );

  const lines = ["## Attached files for this conversation", ...persistedLines, ...inlineImageLines];
  return lines.length > 1 ? lines.join("\n") : null;
}

interface UseChatAttachmentsParams {
  teamId: string;
  sessionId: string | null;
}

export function useChatAttachments({ teamId, sessionId }: UseChatAttachmentsParams) {
  const dispatch = useDispatch();
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);

  const { data: persistedAttachmentsData = [], isFetching: isHydratingAttachments } =
    useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery(
      { teamId, sessionId: sessionId ?? "" },
      { skip: !teamId || !sessionId },
    );

  const [uploadUserFileMutation] = useUploadUserFileKnowledgeFlowV1StorageUserUploadPostMutation();
  const [fastIngestMutation] = useFastIngestKnowledgeFlowV1FastIngestPostMutation();
  const [persistAttachmentMutation] =
    usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation();
  const [deletePersistedAttachmentMutation] =
    useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation();

  const persistedAttachments = useMemo(
    () => (persistedAttachmentsData as SessionAttachmentApiPayload[]).map(toSessionAttachment),
    [persistedAttachmentsData],
  );

  const uploadUserFile = useCallback(
    async (file: File): Promise<UserStorageUploadResult> => {
      const key = safeUploadKey(file);
      const formData = new FormData();
      formData.append("key", key);
      formData.append("file", file);
      const payload = (await uploadUserFileMutation({
        bodyUploadUserFileKnowledgeFlowV1StorageUserUploadPost: formData as never,
      }).unwrap()) as UserStorageUploadResponse;
      return { ...payload, requestedKey: key };
    },
    [uploadUserFileMutation],
  );

  const fastIngestAttachment = useCallback(
    async (file: File, activeSessionId: string | null | undefined): Promise<FastIngestResponse | null> => {
      if (!activeSessionId) return null;

      const formData = new FormData();
      formData.append("file", file);
      formData.append("session_id", activeSessionId);
      formData.append("scope", "session");
      formData.append("options_json", JSON.stringify({ include_summary: true }));

      return (await fastIngestMutation({
        bodyFastIngestKnowledgeFlowV1FastIngestPost: formData as never,
      }).unwrap()) as FastIngestResponse;
    },
    [fastIngestMutation],
  );

  const deletePersistedAttachment = useCallback(
    async (attachmentId: string) => {
      if (!teamId || !sessionId) return;
      setAttachments((prev) => prev.filter((attachment) => attachment.id !== attachmentId));
      await deletePersistedAttachmentMutation({
        teamId,
        sessionId,
        attachmentId,
      }).unwrap();
    },
    [deletePersistedAttachmentMutation, sessionId, teamId],
  );

  const addFiles = useCallback(
    async (files: File[], source: "picker" | "drop", activeSessionId?: string | null) => {
      const uniqueFiles = files.filter((file) => file.size > 0);
      const ingestionSessionId = activeSessionId ?? sessionId;
      for (const file of uniqueFiles) {
        if (!ingestionSessionId) continue;

        const id = uuidv4();
        const localTaskId = `chat-attachment-${id}`;
        const isImage = file.type.startsWith("image/");

        dispatch(
          taskRegistered({
            taskId: localTaskId,
            kind: "ingestion",
            target: { type: "attachment", id, label: file.name },
            localOnly: true,
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

          await persistAttachmentMutation({
            teamId,
            sessionId: ingestionSessionId,
            createSessionAttachmentRequest: {
              attachment_id: id,
              name: file.name,
              mime: file.type || null,
              size_bytes: file.size,
              summary_md: fastIngest?.summary_md || "_(No summary returned by Knowledge Flow)_",
              document_uid: fastIngest?.document_uid || null,
              storage_key: key,
            },
          }).unwrap();

          emitLocalTaskEvent(
            dispatch,
            localTaskId,
            "succeeded",
            {
              type: fastIngest?.document_uid ? "document" : "attachment",
              id: fastIngest?.document_uid ?? id,
              label: file.name,
            },
            "Terminé",
          );

          setAttachments((prev) =>
            prev.map((attachment) =>
              attachment.id === id
                ? {
                    ...attachment,
                    status: "ready",
                    workspacePath: workspacePath(key),
                    imageContext,
                    documentUid: fastIngest?.document_uid,
                    taskIds: [localTaskId],
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
    [dispatch, fastIngestAttachment, persistAttachmentMutation, sessionId, teamId, uploadUserFile],
  );

  const removeAttachment = useCallback(
    (id: string) => {
      setAttachments((prev) => prev.filter((attachment) => attachment.id !== id));
      const persisted = persistedAttachments.find((attachment) => attachment.attachmentId === id);
      if (persisted) {
        void deletePersistedAttachment(id);
      }
    },
    [deletePersistedAttachment, persistedAttachments],
  );

  const clearReadyAttachments = useCallback(() => {
    setAttachments((prev) =>
      prev.filter((attachment) => attachment.status === "uploading" || attachment.status === "ingesting"),
    );
  }, []);

  const attachmentsMarkdown = useMemo(
    () =>
      buildAttachmentsMarkdown(
        persistedAttachments,
        attachments.filter((attachment) => attachment.status === "ready"),
      ),
    [attachments, persistedAttachments],
  );

  return {
    attachments,
    persistedAttachments,
    isHydratingAttachments,
    attachmentsMarkdown,
    addFiles,
    removeAttachment,
    deletePersistedAttachment,
    clearReadyAttachments,
  };
}
