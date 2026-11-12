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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AttachmentChips } from "@shared/molecules/AttachmentChips/AttachmentChips";
import Button from "@shared/atoms/Button/Button";
import ChatSidePanel from "../ChatSidePanel/ChatSidePanel.tsx";
import { formatBytes } from "@shared/utils/formatBytes";
import type { SessionAttachment } from "@rework/types/attachments";
import DocumentPreviewDrawer, { type DocumentPreviewTarget } from "../DocumentPreviewDrawer/DocumentPreviewDrawer";
import type { ConversationFile } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { WorkspaceFile } from "../../../../../slices/runtime/runtimeOpenApi";
import { conversationFileUrl, workspaceFileUrl } from "../../../../features/conversationFiles";
import { downloadAuthed } from "../../../../../utils/downloadUtils";
import styles from "./SessionAttachmentsDrawer.module.css";

interface SessionAttachmentsDrawerProps {
  open: boolean;
  onClose: () => void;
  attachments: SessionAttachment[];
  files?: ConversationFile[];
  workspaceFiles?: WorkspaceFile[];
  workspaceFilesUrl?: string | null;
  workspaceError?: unknown;
  workspaceLoading?: boolean;
  spaceId?: string;
  sessionId?: string;
  filesError?: unknown;
  attachmentsError?: unknown;
  filesLoading?: boolean;
  isLoading?: boolean;
  readOnly?: boolean;
  onRetryFiles?: () => void;
  onRetryAttachments?: () => void;
  onDelete: (attachmentId: string) => Promise<boolean> | void;
}

// Only a numeric HTTP status is safe to display from an untrusted error payload.
// Never render response bodies, exception messages, paths or credentials.
function httpStatus(error: unknown): number | undefined {
  const status = error && typeof error === "object" && "status" in error ? error.status : undefined;
  if (typeof status === "number" && status >= 400 && status <= 599) return status;
  const match = error instanceof Error && /^Download failed \(([45]\d{2})\)$/.exec(error.message);
  return match ? Number(match[1]) : undefined;
}

export function SessionAttachmentsDrawer({
  open,
  onClose,
  attachments,
  files = [],
  workspaceFiles = [],
  workspaceFilesUrl = "",
  workspaceError,
  workspaceLoading = false,
  spaceId = "",
  sessionId = "",
  filesError,
  attachmentsError,
  filesLoading = false,
  isLoading = false,
  readOnly = false,
  onRetryFiles,
  onRetryAttachments,
  onDelete,
}: SessionAttachmentsDrawerProps) {
  const { t } = useTranslation();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [downloading, setDownloading] = useState<Record<string, boolean>>({});
  const [preview, setPreview] = useState<(DocumentPreviewTarget & { key: string }) | null>(null);
  const errorMessage = (key: string, error: unknown) => {
    const status = httpStatus(error);
    return t(`chatbot.sessionAttachments.${key}`) + (status ? ` (HTTP ${status})` : "");
  };
  const download = async (key: string, url: string, name: string) => {
    setDownloading((previous) => ({ ...previous, [key]: true }));
    try {
      await downloadAuthed(url, name);
      setErrors((previous) => ({ ...previous, [`${key}:download`]: "" }));
    } catch (error) {
      setErrors((previous) => ({ ...previous, [`${key}:download`]: errorMessage("downloadError", error) }));
    } finally {
      setDownloading((previous) => ({ ...previous, [key]: false }));
    }
  };
  const remove = async (id: string) => {
    try {
      if ((await onDelete(id)) === false) throw new Error("Deletion refused");
    } catch (error) {
      setErrors((previous) => ({ ...previous, [`sources:${id}:delete`]: errorMessage("deleteError", error) }));
    }
  };
  const sections = [
    {
      key: "workspace",
      error: workspaceError,
      loading: workspaceLoading,
      retry: onRetryFiles,
      errorKey: "workspaceError",
      items: workspaceFiles.map((file) => ({
        id: file.path,
        name: file.path,
        size: file.size,
        modified: file.modified,
        mime: "text/plain",
        status: "ready" as const,
        canRemove: false,
        error: undefined,
        downloadUrl: workspaceFileUrl(workspaceFilesUrl ?? "", file.path),
        preview: {
          documentUid: `workspace:${sessionId}:${file.path}`,
          fileName: file.name,
          sourceUrl: workspaceFileUrl(workspaceFilesUrl ?? "", file.path),
          sourceFormat: "text" as const,
        },
      })),
    },
    {
      key: "deliverables",
      error: filesError,
      loading: filesLoading,
      retry: onRetryFiles,
      errorKey: "filesError",
      items: files.map((file) => ({
        id: file.document_id,
        name: file.name,
        size: file.size,
        modified: undefined,
        mime: file.mime,
        status: "ready" as const,
        canRemove: false,
        error: undefined,
        downloadUrl: conversationFileUrl(spaceId, sessionId, file.document_id),
        preview:
          file.preview_content_id || file.mime === "application/pdf"
            ? {
                documentUid: file.document_id,
                fileName: file.name,
                sourceUrl: conversationFileUrl(spaceId, sessionId, file.document_id, !!file.preview_content_id),
              }
            : null,
      })),
    },
    {
      key: "sources",
      error: attachmentsError,
      loading: isLoading,
      retry: onRetryAttachments,
      errorKey: "attachmentsError",
      items: attachments.map((attachment) => ({
        id: attachment.attachmentId,
        name: attachment.name,
        size: attachment.sizeBytes,
        modified: undefined,
        mime: attachment.mime ?? "",
        status: attachment.status,
        error: attachment.error,
        canRemove: !readOnly && attachment.status !== "ingesting",
        downloadUrl: attachment.documentUid
          ? `/control-plane/v1/spaces/${encodeURIComponent(spaceId)}/sessions/${encodeURIComponent(attachment.sessionId ?? sessionId)}/attachments/${encodeURIComponent(attachment.documentUid)}/content`
          : null,
        preview:
          attachment.documentUid && attachment.status === "ready"
            ? { documentUid: attachment.documentUid, sessionId: attachment.sessionId, fileName: attachment.name }
            : null,
      })),
    },
  ];
  const visibleSections = sections.filter((section) => section.items.length || section.error || section.loading);

  return (
    <>
      <ChatSidePanel
        open={open}
        onClose={onClose}
        title={t("chatbot.sessionAttachments.title")}
        persistKey="session-attachments-panel"
      >
        {visibleSections.length === 0 && <p className={styles.empty}>{t("chatbot.sessionAttachments.empty")}</p>}
        {visibleSections.map((section) => (
          <section
            className={styles.list}
            key={section.key}
            aria-label={t(`chatbot.sessionAttachments.${section.key}`)}
          >
            <h3 className={styles.heading}>{t(`chatbot.sessionAttachments.${section.key}`)}</h3>
            {!!section.error && (
              <div className={styles.error} role="alert">
                <p>{errorMessage(section.errorKey, section.error)}</p>
                {section.retry && (
                  <Button
                    size="small"
                    variant="outlined"
                    color="secondary"
                    disabled={section.loading}
                    onClick={section.retry}
                  >
                    {t("common.retry")}
                  </Button>
                )}
              </div>
            )}
            {section.loading && (
              <p className={styles.empty} role="status">
                {t("chatbot.sessionAttachments.loading")}
              </p>
            )}
            {section.items.map((file) => {
              const key = `${section.key}:${file.id}`;
              return (
                <div className={styles.file} key={key}>
                  <AttachmentChips
                    stacked
                    attachments={[
                      { ...file, size: file.size ?? 0, detail: file.size == null ? undefined : formatBytes(file.size) },
                    ]}
                    onRemove={(id) => void remove(id)}
                  />
                  {file.modified && (
                    <time className={styles.empty} dateTime={file.modified}>
                      {new Date(file.modified).toLocaleString()}
                    </time>
                  )}
                  {file.status === "error" && (
                    <p className={styles.error} role="alert">
                      {t("chatbot.sessionAttachments.preparationError")}
                      {file.error && t(`chatbot.attachments.errors.${file.error}`, { defaultValue: "" })}
                    </p>
                  )}
                  <div className={styles.actions}>
                    {file.preview && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="secondary"
                        onClick={() => setPreview({ ...file.preview!, key })}
                      >
                        {t("chatbot.sessionAttachments.preview")}
                      </Button>
                    )}
                    {file.downloadUrl && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="secondary"
                        disabled={downloading[key]}
                        onClick={() => void download(key, file.downloadUrl!, file.name)}
                      >
                        {t("chatbot.sessionAttachments.download")}
                      </Button>
                    )}
                  </div>
                  {["preview", "download", "delete"].map(
                    (action) =>
                      errors[`${key}:${action}`] && (
                        <p key={action} className={styles.error} role="alert">
                          {errors[`${key}:${action}`]}
                        </p>
                      ),
                  )}
                </div>
              );
            })}
          </section>
        ))}
      </ChatSidePanel>
      {preview && (
        <DocumentPreviewDrawer
          key={preview.key}
          target={preview}
          onClose={() => setPreview(null)}
          onError={(error) =>
            setErrors((previous) => ({ ...previous, [`${preview.key}:preview`]: errorMessage("previewError", error) }))
          }
          onLoaded={() => setErrors((previous) => ({ ...previous, [`${preview.key}:preview`]: "" }))}
        />
      )}
    </>
  );
}
