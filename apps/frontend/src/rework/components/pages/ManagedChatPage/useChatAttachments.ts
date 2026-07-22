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

import { useCallback, useEffect, useMemo, useState } from "react";
import { useDispatch } from "react-redux";
import { useTranslation } from "react-i18next";
import { v4 as uuidv4 } from "uuid";
import { useFastIngestKnowledgeFlowV1FastIngestPostMutation } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation,
  useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery,
  usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { taskEventReceived, taskRegistered } from "../../../features/tasks/taskSlice";
import type { ChatAttachment, ChatImageContext, SessionAttachment } from "@rework/types/attachments";

const MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024;
const ALLOWED_INLINE_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

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

function toSessionAttachment(payload: SessionAttachmentApiPayload): SessionAttachment {
  return {
    attachmentId: payload.attachment_id ?? "",
    name: payload.name ?? "Attachment",
    mime: payload.mime ?? undefined,
    sizeBytes: payload.size_bytes ?? undefined,
    summaryMd: payload.summary_md ?? "",
    documentUid: payload.document_uid ?? undefined,
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

export function buildAttachmentsMarkdown(persisted: SessionAttachment[], transient: ChatAttachment[]): string | null {
  // Persisted files are ingested for this session, so the agent can find them via
  // document search. Inline image data is only listed as metadata here; the runtime
  // must not place raw data URLs in the system prompt.
  // The bracketed identifier is the internal document uid: the agent context is an
  // internal surface, so carrying it here is fine — document tools accept the
  // file name and resolve internally, and also tolerate this bracketed form.
  const uidSuffix = (documentUid?: string) => (documentUid ? ` [${documentUid}]` : "");
  const persistedLines = persisted.map(
    (attachment) => `- ${attachment.name}${uidSuffix(attachment.documentUid)}: conversation document`,
  );
  const inlineImageLines = transient.flatMap((attachment) =>
    attachment.imageContext
      ? [
          `- ${attachment.name}${uidSuffix(attachment.documentUid)}: conversation image (${attachment.imageContext.mime}, ${attachment.imageContext.size} bytes)`,
          `  data: ${attachment.imageContext.dataUrl}`,
        ]
      : [],
  );

  const lines = ["## Attached files for this conversation", ...persistedLines, ...inlineImageLines];
  return lines.length > 1 ? lines.join("\n") : null;
}

export function excludeDeletedAttachments(
  persisted: SessionAttachment[],
  deletedAttachmentIds: ReadonlySet<string>,
): SessionAttachment[] {
  return persisted.filter((attachment) => !deletedAttachmentIds.has(attachment.attachmentId));
}

interface UseChatAttachmentsParams {
  teamId: string;
  sessionId: string | null;
}

export function useChatAttachments({ teamId, sessionId }: UseChatAttachmentsParams) {
  const dispatch = useDispatch();
  const { t } = useTranslation();
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [deletedAttachmentIds, setDeletedAttachmentIds] = useState<ReadonlySet<string>>(new Set());

  useEffect(() => {
    setDeletedAttachmentIds(new Set());
  }, [sessionId]);

  const { data: persistedAttachmentsData = [], isFetching: isHydratingAttachments } =
    useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery(
      { teamId, sessionId: sessionId ?? "" },
      { skip: !teamId || !sessionId },
    );

  const [fastIngestMutation] = useFastIngestKnowledgeFlowV1FastIngestPostMutation();
  const [persistAttachmentMutation] =
    usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation();
  const [deletePersistedAttachmentMutation] =
    useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation();

  const persistedAttachments = useMemo(
    () =>
      excludeDeletedAttachments(
        (persistedAttachmentsData as SessionAttachmentApiPayload[]).map(toSessionAttachment),
        deletedAttachmentIds,
      ),
    [deletedAttachmentIds, persistedAttachmentsData],
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
      setDeletedAttachmentIds((prev) => new Set(prev).add(attachmentId));
      try {
        await deletePersistedAttachmentMutation({
          teamId,
          sessionId,
          attachmentId,
        }).unwrap();
      } catch (error) {
        setDeletedAttachmentIds((prev) => {
          const next = new Set(prev);
          next.delete(attachmentId);
          return next;
        });
        throw error;
      }
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
          source === "drop" ? t("chatbot.attachments.processingPrepare") : t("chatbot.attachments.processingFast"),
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
          const [imageContext, fastIngest] = await Promise.all([
            readImageContext(file),
            fastIngestAttachment(file, ingestionSessionId),
          ]);

          await persistAttachmentMutation({
            teamId,
            sessionId: ingestionSessionId,
            createSessionAttachmentRequest: {
              attachment_id: id,
              name: file.name,
              mime: file.type || null,
              size_bytes: file.size,
              summary_md: fastIngest?.summary_md || t("chatbot.sessionAttachments.noSummary"),
              document_uid: fastIngest?.document_uid || null,
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
            t("chatbot.attachments.processingDone"),
          );

          setAttachments((prev) =>
            prev.map((attachment) =>
              attachment.id === id
                ? {
                    ...attachment,
                    status: "ready",
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
            t("chatbot.attachments.processingFailed"),
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
    [dispatch, fastIngestAttachment, persistAttachmentMutation, sessionId, t, teamId],
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

  // True while any attachment is still uploading/ingesting. Used to block message
  // send until every attachment has finished, so the agent never answers before
  // its ingested content is retrievable.
  const hasUploadingAttachments = useMemo(
    () => attachments.some((attachment) => attachment.status === "uploading" || attachment.status === "ingesting"),
    [attachments],
  );

  return {
    attachments,
    persistedAttachments,
    isHydratingAttachments,
    attachmentsMarkdown,
    hasUploadingAttachments,
    addFiles,
    removeAttachment,
    deletePersistedAttachment,
    clearReadyAttachments,
  };
}
