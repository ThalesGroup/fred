// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useDispatch } from "react-redux";
import { useTranslation } from "react-i18next";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import {
  useListAttachmentsQuery,
  useDeleteAttachmentMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Attachment } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { managerActor, type ManagerDispatch } from "../../../features/imports/managerImportRun";
import type { AttachmentSource, ChatAttachment, SessionAttachment } from "@rework/types/attachments";
import {
  attachmentErrorCode,
  attachmentUploadScope,
  forgetAttachmentUpload,
  refreshAttachmentUploads,
  retryAttachmentUpload,
  uploadAttachments,
  type UploadScope,
} from "./attachmentUploads";

export function attachmentStatus(document: Attachment): ChatAttachment["status"] {
  if (document.ready) return "ready";
  if (document.processing?.status === "pending" || document.processing?.status === "running") return "ingesting";
  return "error";
}
interface UseChatAttachmentsParams {
  enabled?: boolean;
  canUpload?: boolean;
  spaceId: string;
  sessionId: string | null;
}
export function useChatAttachments({ spaceId, sessionId, enabled = true, canUpload = true }: UseChatAttachmentsParams) {
  const dispatch = useDispatch<ManagerDispatch>();
  const { t } = useTranslation();
  const { notifyApiError } = useApiErrorToast();
  const actor = managerActor();
  const scope = useMemo(() => attachmentUploadScope(actor, spaceId, sessionId ?? ""), [actor, spaceId, sessionId]);
  const [acceptedDeletions, setAcceptedDeletions] = useState<{ scope: UploadScope; ids: ReadonlySet<string> }>({
    scope,
    ids: new Set(),
  });
  const visibleScope = useRef<UploadScope | null>(scope);
  visibleScope.current = scope;
  useEffect(() => {
    visibleScope.current = scope;
    return () => {
      visibleScope.current = null;
    };
  }, [scope]);
  const subscribe = useCallback(
    (listener: () => void) => {
      scope.listeners.add(listener);
      return () => {
        scope.listeners.delete(listener);
      };
    },
    [scope],
  );
  const snapshot = useCallback(() => scope.entries, [scope]);
  const uploads = useSyncExternalStore(subscribe, snapshot);
  const {
    currentData: listedDocuments,
    isFetching,
    refetch,
    error: listError,
  } = useListAttachmentsQuery(
    { spaceId, sessionId: sessionId ?? "" },
    { skip: !enabled || !spaceId || !sessionId, refetchOnMountOrArgChange: true },
  );
  const documents = useMemo(
    () =>
      listedDocuments?.filter((d) => acceptedDeletions.scope !== scope || !acceptedDeletions.ids.has(d.document_id)),
    [acceptedDeletions, listedDocuments, scope],
  );
  const [deleteDocument] = useDeleteAttachmentMutation();
  const needsFollowup =
    uploads.some((e) => e.phase === "uncertain" || e.phase === "stored" || e.phase === "uploading") ||
    documents?.some((d) => attachmentStatus(d) === "ingesting");

  // One owner polls receipts and the canonical list; chips and drawer only render.
  useEffect(() => {
    if (!enabled || !spaceId || !sessionId || !needsFollowup) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        await refreshAttachmentUploads(dispatch, scope);
        if (stopped || managerActor() !== actor) return;
        await refetch();
      } finally {
        if (!stopped)
          timer = setTimeout(() => {
            void poll();
          }, 3000);
      }
    };
    timer = setTimeout(() => {
      void poll();
    }, 3000);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [actor, dispatch, enabled, needsFollowup, refetch, scope, sessionId, spaceId]);

  useEffect(() => {
    if (!documents) return;
    for (const entry of uploads) {
      if (entry.phase === "stored" && documents.some((d) => d.document_id === entry.receipt?.document_id))
        forgetAttachmentUpload(scope, entry.key);
    }
  }, [documents, scope, uploads]);

  const attachments: ChatAttachment[] = [
    ...(documents ?? []).map(
      (document): ChatAttachment => ({
        id: document.document_id,
        name: document.name,
        size: document.size,
        mime: document.mime,
        status: attachmentStatus(document),
        isImage: document.mime.startsWith("image/"),
        documentUid: document.document_id,
        error: document.processing?.error_code ?? (attachmentStatus(document) === "error" ? "not_ready" : undefined),
      }),
    ),
    ...uploads
      .filter((entry) => !documents?.some((d) => d.document_id === entry.receipt?.document_id))
      .map(
        (entry): ChatAttachment => ({
          id: entry.key,
          name: entry.name,
          size: entry.size,
          mime: entry.mime,
          status: entry.phase === "failed" ? "error" : entry.phase === "stored" ? "ingesting" : "uploading",
          isImage: entry.mime.startsWith("image/"),
          error: entry.error,
          canRetry: entry.phase === "failed" || entry.phase === "uncertain",
          canRemove: entry.phase === "failed",
        }),
      ),
  ];
  const persistedAttachments: SessionAttachment[] = (documents ?? []).map((d) => ({
    attachmentId: d.document_id,
    name: d.name,
    mime: d.mime,
    sizeBytes: d.size,
    documentUid: d.document_id,
    summaryMd: "",
    createdAt: d.created_at,
    status: attachmentStatus(d),
    error: d.processing?.error_code ?? undefined,
  }));
  const deletePersistedAttachment = useCallback(
    async (documentId: string) => {
      if (!enabled || !sessionId || managerActor() !== actor) return;
      try {
        await deleteDocument({ spaceId, sessionId, documentId }).unwrap();
        if (managerActor() !== actor) return;
        if (visibleScope.current === scope)
          setAcceptedDeletions((previous) => ({
            scope,
            ids: new Set([...(previous.scope === scope ? previous.ids : []), documentId]),
          }));
        // Only the accepted lifecycle receipt authorizes removal; physical purge is separate.
        for (const entry of scope.entries)
          if (entry.receipt?.document_id === documentId) forgetAttachmentUpload(scope, entry.key);
      } catch (error) {
        if (managerActor() === actor && visibleScope.current === scope)
          notifyApiError(error, {
            summary: t("chatbot.errors.attachmentDeleteFailedSummary"),
            fallbackDetail: t("chatbot.errors.attachmentDeleteFailedDetail"),
            conflictDetail: t(`chatbot.attachments.errors.${attachmentErrorCode(error)}`, {
              defaultValue: t("chatbot.errors.attachmentDeleteFailedDetail"),
            }),
          });
      }
    },
    [actor, deleteDocument, enabled, notifyApiError, scope, sessionId, spaceId, t],
  );
  const addFiles = useCallback(
    async (files: File[], _source: AttachmentSource, activeSessionId?: string | null) => {
      const sid = activeSessionId ?? sessionId;
      if (!enabled || !canUpload || !sid || !spaceId || managerActor() !== actor) return;
      try {
        await uploadAttachments(dispatch, attachmentUploadScope(actor, spaceId, sid), files);
      } catch (error) {
        if (managerActor() === actor && visibleScope.current === scope)
          notifyApiError(error, {
            summary: t("chatbot.errors.attachmentUploadFailedDetail"),
            fallbackDetail: t("chatbot.errors.attachmentUploadFailedDetail"),
          });
      }
    },
    [actor, canUpload, dispatch, enabled, notifyApiError, scope, sessionId, spaceId, t],
  );
  const retryUpload = useCallback(
    async (id: string, file: File) => {
      if (!enabled || !canUpload || managerActor() !== actor) return;
      try {
        await retryAttachmentUpload(dispatch, scope, id, file);
      } catch (error) {
        if (managerActor() === actor && visibleScope.current === scope)
          notifyApiError(error, {
            summary: t("chatbot.errors.attachmentUploadFailedDetail"),
            fallbackDetail: t("chatbot.errors.attachmentUploadFailedDetail"),
          });
      }
    },
    [actor, canUpload, dispatch, enabled, notifyApiError, scope, t],
  );
  const removeAttachment = useCallback(
    (id: string) => {
      const local = scope.entries.find((e) => e.key === id);
      if (local?.phase === "failed") forgetAttachmentUpload(scope, id);
      else if (!local) void deletePersistedAttachment(id);
    },
    [deletePersistedAttachment, scope],
  );
  return {
    attachments,
    persistedAttachments,
    isHydratingAttachments: isFetching,
    listError,
    refreshAttachments: refetch,
    hasReadyAttachments: attachments.some((a) => a.status === "ready"),
    hasUploadingAttachments:
      enabled &&
      canUpload &&
      (Boolean(sessionId && !documents) ||
        attachments.some((a) => a.status === "uploading" || a.status === "ingesting")),
    addFiles,
    retryUpload,
    removeAttachment,
    deletePersistedAttachment,
  };
}
