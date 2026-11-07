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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AttachmentChips } from "@shared/molecules/AttachmentChips/AttachmentChips";
import UploadWarningBanner from "@shared/molecules/UploadWarningBanner/UploadWarningBanner";
import ChatSidePanel from "../ChatSidePanel/ChatSidePanel.tsx";
import { MarkdownPreviewModal } from "../MarkdownPreviewModal/MarkdownPreviewModal";
import { formatBytes as formatBytesUnit } from "@shared/utils/formatBytes";
import type { SessionAttachment } from "@rework/types/attachments";
import DocumentPreviewDrawer from "../DocumentPreviewDrawer/DocumentPreviewDrawer";
import { isEmailFile } from "../../../../utils/documentViewerUtils";
import type { ConversationFile } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { conversationFileUrl } from "../../../../features/conversationFiles";
import { downloadAuthed } from "../../../../../utils/downloadUtils";
import { useToast } from "../Toast/ToastProvider";
import styles from "./SessionAttachmentsDrawer.module.css";

interface SessionAttachmentsDrawerProps {
  open: boolean;
  onClose: () => void;
  attachments: SessionAttachment[];
  files?: ConversationFile[];
  spaceId?: string;
  sessionId?: string;
  filesError?: boolean;
  filesLoading?: boolean;
  isLoading?: boolean;
  readOnly?: boolean;
  onDelete: (attachmentId: string) => void;
}

function formatBytes(value?: number): string | null {
  if (!value || value <= 0) return null;
  return formatBytesUnit(value);
}

function formatTimestamp(value?: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString();
}

export function SessionAttachmentsDrawer({
  open,
  onClose,
  attachments,
  files = [],
  spaceId = "",
  sessionId = "",
  filesError = false,
  filesLoading = false,
  isLoading = false,
  readOnly = false,
  onDelete,
}: SessionAttachmentsDrawerProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const download = async (id: string) => {
    const file = files.find((item) => item.document_id === id);
    if (!file) return;
    try {
      await downloadAuthed(conversationFileUrl(spaceId, sessionId, id), file.name);
    } catch {
      showError({ summary: t("chatbot.sessionAttachments.downloadError") });
    }
  };
  const [previewAttachmentId, setPreviewAttachmentId] = useState<string | null>(null);

  useEffect(() => {
    if (!previewAttachmentId) return;
    if (!attachments.some((attachment) => attachment.attachmentId === previewAttachmentId)) {
      setPreviewAttachmentId(null);
    }
  }, [attachments, previewAttachmentId]);

  const previewAttachment = useMemo(
    () => attachments.find((attachment) => attachment.attachmentId === previewAttachmentId) ?? null,
    [attachments, previewAttachmentId],
  );

  return (
    <>
      <ChatSidePanel
        open={open}
        onClose={onClose}
        title={t("chatbot.sessionAttachments.title")}
        persistKey="session-attachments-panel"
        fill
      >
        <div className={styles.hint}>{t("chatbot.sessionAttachments.deliverables")}</div>
        {filesError ? (
          <div className={styles.empty} role="alert">
            {t("chatbot.sessionAttachments.filesError")}
          </div>
        ) : files.length === 0 ? (
          <div className={styles.empty}>
            {t(filesLoading ? "chatbot.sessionAttachments.loading" : "chatbot.sessionAttachments.noDeliverables")}
          </div>
        ) : (
          <AttachmentChips
            stacked
            attachments={files.map((file) => ({
              id: file.document_id,
              name: file.path,
              size: file.size,
              mime: file.mime,
              status: "ready" as const,
              canRemove: false,
              detail: [formatBytes(file.size), formatTimestamp(file.updated_at)].filter(Boolean).join(" · "),
            }))}
            onOpen={(id) => void download(id)}
            onRemove={() => undefined}
          />
        )}
        <div className={styles.hint}>{t("chatbot.sessionAttachments.sources")}</div>
        <UploadWarningBanner />
        <div className={styles.hint}>{t("chatbot.attachments.readyHint")}</div>
        <div className={styles.list}>
          {isLoading && attachments.length === 0 ? (
            <div className={styles.empty}>{t("chatbot.sessionAttachments.loading")}</div>
          ) : attachments.length === 0 ? (
            <div className={styles.empty}>{t("chatbot.sessionAttachments.empty")}</div>
          ) : (
            <AttachmentChips
              stacked
              attachments={attachments.map((attachment) => ({
                id: attachment.attachmentId,
                name: attachment.name,
                size: attachment.sizeBytes ?? 0,
                mime: attachment.mime ?? "",
                status: attachment.status,
                error: attachment.error,
                canRemove: !readOnly && attachment.status !== "ingesting",
                detail: [formatBytes(attachment.sizeBytes), formatTimestamp(attachment.createdAt)]
                  .filter(Boolean)
                  .join(" · "),
              }))}
              onRemove={onDelete}
              onOpen={setPreviewAttachmentId}
            />
          )}
        </div>
      </ChatSidePanel>
      {previewAttachment?.documentUid && previewAttachment.sessionId && isEmailFile(previewAttachment.name) ? (
        <DocumentPreviewDrawer
          target={{
            documentUid: previewAttachment.documentUid,
            sessionId: previewAttachment.sessionId,
            fileName: previewAttachment.name,
          }}
          onClose={() => setPreviewAttachmentId(null)}
        />
      ) : (
        <MarkdownPreviewModal
          open={previewAttachment != null}
          onClose={() => setPreviewAttachmentId(null)}
          title={previewAttachment?.name ?? t("chatbot.sessionAttachments.filePreviewTitle")}
          subtitle={[
            previewAttachment?.mime,
            formatBytes(previewAttachment?.sizeBytes),
            formatTimestamp(previewAttachment?.createdAt),
          ]
            .filter(Boolean)
            .join(" · ")}
          markdown={previewAttachment?.summaryMd || t("chatbot.sessionAttachments.noSummary")}
        />
      )}
    </>
  );
}
