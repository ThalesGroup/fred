// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useDispatch, useStore } from "react-redux";
import { useTranslation } from "react-i18next";
import { fetchAuthedBlob } from "../../../../utils/downloadUtils";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useListAttachmentsQuery,
  useDeleteAttachmentMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Attachment } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { managerActor, type ManagerDispatch } from "../../../features/imports/managerImportRun";
import type { AttachmentSource, ChatAttachment, SessionAttachment } from "@rework/types/attachments";
import {
  attachmentUploadScope,
  dismissAttachment,
  forgetAttachmentUpload,
  refreshAttachmentUploads,
  retryAttachmentUpload,
  uploadAttachments,
  type UploadScope,
} from "./attachmentUploads";

import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../../common/capabilityRoutingSlice";
import { chatAttachmentHandlersForCapabilities } from "../../../features/capabilities/chatAttachmentRegistry";
import type { ChatAttachmentContext, ChatAttachmentForget } from "../../../features/capabilities/types";

const NO_CAPABILITIES: readonly string[] = [];

export function attachmentStatus(document: Attachment): ChatAttachment["status"] {
  if (document.ready) return "ready";
  if (document.processing?.status === "pending" || document.processing?.status === "running") return "ingesting";
  return "error";
}
function documentError(document: Attachment) {
  return document.processing?.error_code ?? (attachmentStatus(document) === "error" ? "not_ready" : undefined);
}
interface UseChatAttachmentsParams {
  enabled?: boolean;
  canUpload?: boolean;
  spaceId: string;
  sessionId: string | null;
  /** Epoch ms of the latest turn: ready documents created up to then were already sent. */
  sentBefore?: number;
  capabilityIds?: readonly string[];
}
export function useChatAttachments({
  spaceId,
  sessionId,
  enabled = true,
  canUpload = true,
  sentBefore = 0,
  capabilityIds = NO_CAPABILITIES,
}: UseChatAttachmentsParams) {
  const dispatch = useDispatch<ManagerDispatch>();
  const store = useStore<{ capabilityRouting: CapabilityRoutingState }>();
  const capabilities = useRef(capabilityIds);
  capabilities.current = capabilityIds;
  const capabilityCopies = useRef(new Map<string, ChatAttachmentForget[]>());
  const notifyCapabilities = useCallback(
    async (file: File, sid: string, documentId: string, activeCapabilities: readonly string[]) => {
      const key = `${spaceId}/${sid}/${documentId}`;
      if (capabilityCopies.current.has(key)) return;
      capabilityCopies.current.set(key, []);
      const copies = await Promise.all(
        chatAttachmentHandlersForCapabilities(activeCapabilities).map(async ({ capabilityId, handle }) => {
          const baseUrl = selectCapabilityBaseUrl(store.getState(), capabilityId);
          if (!baseUrl) return;
          try {
            return await handle(file, {
              capabilityId,
              baseUrl,
              teamId: spaceId,
              sessionId: sid,
              dispatch: dispatch as ChatAttachmentContext["dispatch"],
            });
          } catch (error) {
            console.warn("[chat attachments] capability copy failed", capabilityId, error);
          }
        }),
      );
      const kept = copies.filter((copy): copy is ChatAttachmentForget => typeof copy === "function");
      if (capabilityCopies.current.has(key)) {
        if (kept.length) capabilityCopies.current.set(key, kept);
        else capabilityCopies.current.delete(key);
      } else await Promise.allSettled(kept.map((forget) => forget()));
    },
    [dispatch, spaceId, store],
  );
  const { t } = useTranslation();
  const { notifyApiError } = useApiErrorToast();
  const { showError } = useToast();
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
  // Replay capability copies from accepted originals after an uncertain upload or reload.
  // The capability's hash deduplication makes this harmless when the first copy succeeded.
  const recovering = useRef(new Set<string>());
  const [recoveryAttempt, setRecoveryAttempt] = useState(0);
  useEffect(() => {
    if (!enabled || !sessionId || !documents || !capabilities.current.includes("word_template")) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    void (async () => {
      for (const document of documents) {
        if (stopped || managerActor() !== actor) return;
        if (!/^image\/(png|jpeg|gif)$/.test(document.mime) || document.size > 10 * 1024 * 1024) continue;
        const key = `${spaceId}/${sessionId}/${document.document_id}`;
        if (capabilityCopies.current.has(key) || recovering.current.has(key)) continue;
        recovering.current.add(key);
        try {
          const blob = await fetchAuthedBlob(
            `/control-plane/v1/spaces/${encodeURIComponent(spaceId)}/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(document.document_id)}/content`,
          );
          if (!stopped && managerActor() === actor)
            await notifyCapabilities(
              new File([blob], document.name, { type: document.mime }),
              sessionId,
              document.document_id,
              capabilities.current,
            );
        } catch (error) {
          console.warn("[chat attachments] capability copy recovery failed", error);
        } finally {
          recovering.current.delete(key);
        }
      }
      if (
        !stopped &&
        documents.some(
          (document) =>
            /^image\/(png|jpeg|gif)$/.test(document.mime) &&
            document.size <= 10 * 1024 * 1024 &&
            !capabilityCopies.current.has(`${spaceId}/${sessionId}/${document.document_id}`),
        )
      )
        timer = setTimeout(() => setRecoveryAttempt((attempt) => attempt + 1), 30_000);
    })();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [actor, documents, enabled, notifyCapabilities, recoveryAttempt, sessionId, spaceId]);

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

  const isPending = (document: Attachment) => {
    const status = attachmentStatus(document);
    if (status === "error") return !scope.dismissed.has(document.document_id);
    return status === "ingesting" || Date.parse(document.created_at) > sentBefore;
  };
  // The composer's view: only what the next turn still has to deal with.
  const attachments: ChatAttachment[] = [
    ...(documents ?? []).filter(isPending).map(
      (document): ChatAttachment => ({
        id: document.document_id,
        name: document.name,
        size: document.size,
        mime: document.mime,
        status: attachmentStatus(document),
        documentUid: document.document_id,
        error: documentError(document),
        // The server refuses the deletion while processing runs.
        canRemove: attachmentStatus(document) !== "ingesting",
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
          error: entry.error,
          canRetry: entry.phase === "failed" || entry.phase === "uncertain",
          canRemove: entry.phase === "failed",
        }),
      ),
  ];
  const persistedAttachments = useMemo(
    (): SessionAttachment[] =>
      (documents ?? []).map((d) => ({
        sessionId: sessionId ?? undefined,
        attachmentId: d.document_id,
        name: d.name,
        mime: d.mime,
        sizeBytes: d.size,
        documentUid: d.document_id,
        summaryMd: "",
        createdAt: d.created_at,
        status: attachmentStatus(d),
        error: documentError(d),
      })),
    [documents, sessionId],
  );
  const deletePersistedAttachment = useCallback(
    async (documentId: string) => {
      if (!enabled || !sessionId || managerActor() !== actor) return false;
      try {
        await deleteDocument({ spaceId, sessionId, documentId }).unwrap();
        if (managerActor() !== actor) return false;
        if (visibleScope.current === scope)
          setAcceptedDeletions((previous) => ({
            scope,
            ids: new Set([...(previous.scope === scope ? previous.ids : []), documentId]),
          }));
        const copyKey = `${spaceId}/${sessionId}/${documentId}`;
        const copies = capabilityCopies.current.get(copyKey) ?? [];
        capabilityCopies.current.delete(copyKey);
        await Promise.allSettled(copies.map((forget) => forget()));
        // Only the accepted lifecycle receipt authorizes removal; physical purge is separate.
        for (const entry of scope.entries)
          if (entry.receipt?.document_id === documentId) forgetAttachmentUpload(scope, entry.key);
        return true;
      } catch (error) {
        if (managerActor() === actor && visibleScope.current === scope)
          showError({
            summary: t("chatbot.errors.attachmentDeleteFailedSummary"),
            detail: t(`chatbot.attachments.errors.${(error as { data?: { code?: string } }).data?.code}`, {
              defaultValue: t("chatbot.errors.attachmentDeleteFailedDetail"),
            }),
          });
        return false;
      }
    },
    [actor, deleteDocument, enabled, scope, sessionId, showError, spaceId, t],
  );
  const addFiles = useCallback(
    async (files: File[], _source: AttachmentSource, activeSessionId?: string | null) => {
      const sid = activeSessionId ?? sessionId;
      if (!enabled || !canUpload || !sid || !spaceId || managerActor() !== actor) return;
      const activeCapabilities = capabilities.current;
      try {
        await uploadAttachments(dispatch, attachmentUploadScope(actor, spaceId, sid), files, (file, documentId) =>
          notifyCapabilities(file, sid, documentId, activeCapabilities),
        );
      } catch (error) {
        if (managerActor() === actor && visibleScope.current === scope)
          notifyApiError(error, {
            summary: t("chatbot.errors.attachmentUploadFailedDetail"),
            fallbackDetail: t("chatbot.errors.attachmentUploadFailedDetail"),
          });
      }
    },
    [actor, canUpload, dispatch, enabled, notifyApiError, notifyCapabilities, scope, sessionId, spaceId, t],
  );
  const retryUpload = useCallback(
    async (id: string, file: File) => {
      if (!enabled || !canUpload || managerActor() !== actor) return;
      const activeCapabilities = capabilities.current;
      try {
        await retryAttachmentUpload(dispatch, scope, id, file, (storedFile, documentId) =>
          notifyCapabilities(storedFile, scope.sessionId, documentId, activeCapabilities),
        );
      } catch (error) {
        if (managerActor() === actor && visibleScope.current === scope)
          notifyApiError(error, {
            summary: t("chatbot.errors.attachmentUploadFailedDetail"),
            fallbackDetail: t("chatbot.errors.attachmentUploadFailedDetail"),
          });
      }
    },
    [actor, canUpload, dispatch, enabled, notifyApiError, notifyCapabilities, scope, t],
  );
  const removeAttachment = useCallback(
    (id: string) => {
      const local = scope.entries.find((e) => e.key === id);
      const failedDocument = documents?.some((d) => d.document_id === id && attachmentStatus(d) === "error");
      if (local?.phase === "failed") forgetAttachmentUpload(scope, id);
      else if (!local) {
        // Out of the composer even if the deletion is refused: a failed file is no use there.
        if (failedDocument) dismissAttachment(scope, id);
        void deletePersistedAttachment(id);
      }
    },
    [deletePersistedAttachment, documents, scope],
  );
  return {
    attachments,
    persistedAttachments,
    isHydratingAttachments: isFetching,
    listError,
    refreshAttachments: refetch,
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
