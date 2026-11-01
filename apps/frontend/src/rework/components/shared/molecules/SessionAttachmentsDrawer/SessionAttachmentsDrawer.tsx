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
import styles from "./SessionAttachmentsDrawer.module.css";

interface SessionAttachmentsDrawerProps {
  open: boolean;
  onClose: () => void;
  attachments: SessionAttachment[];
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
  isLoading = false,
  readOnly = false,
  onDelete,
}: SessionAttachmentsDrawerProps) {
  const { t } = useTranslation();
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
        width="460px"
        fill
      >
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
    </>
  );
}
