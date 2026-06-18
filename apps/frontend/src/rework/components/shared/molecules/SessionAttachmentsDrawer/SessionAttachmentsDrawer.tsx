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
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { InlineDrawer } from "../InlineDrawer/InlineDrawer";
import { MarkdownPreviewModal } from "../MarkdownPreviewModal/MarkdownPreviewModal";
import type { SessionAttachment } from "@rework/types/attachments";
import styles from "./SessionAttachmentsDrawer.module.css";

interface SessionAttachmentsDrawerProps {
  open: boolean;
  onClose: () => void;
  attachments: SessionAttachment[];
  isLoading?: boolean;
  onDelete: (attachmentId: string) => void;
}

function formatBytes(value?: number): string | null {
  if (!value || value <= 0) return null;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 102.4) / 10} KB`;
  return `${Math.round(value / (1024 * 102.4)) / 10} MB`;
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
      <InlineDrawer
        open={open}
        onClose={onClose}
        title={t("chatbot.sessionAttachments.title")}
        width="460px"
        layout="push"
      >
        <div className={styles.list}>
          {isLoading && attachments.length === 0 ? (
            <div className={styles.empty}>{t("chatbot.sessionAttachments.loading")}</div>
          ) : attachments.length === 0 ? (
            <div className={styles.empty}>{t("chatbot.sessionAttachments.empty")}</div>
          ) : (
            attachments.map((attachment) => {
              const sizeLabel = formatBytes(attachment.sizeBytes);
              const timestampLabel = formatTimestamp(attachment.createdAt);
              const metaLabel = [attachment.mime, sizeLabel, timestampLabel].filter(Boolean).join(" · ");
              return (
                <button
                  key={attachment.attachmentId}
                  type="button"
                  className={styles.row}
                  onClick={() => setPreviewAttachmentId(attachment.attachmentId)}
                >
                  <span className={styles.rowIcon} aria-hidden>
                    <Icon category="outlined" type="attach_file" />
                  </span>
                  <span className={styles.rowBody}>
                    <span className={styles.rowName} title={attachment.name}>
                      {attachment.name}
                    </span>
                    <span className={styles.rowMeta}>{metaLabel}</span>
                  </span>
                  <span className={styles.rowButtons}>
                    <IconButton
                      color="on-surface"
                      variant="icon"
                      size="xs"
                      icon={{ category: "outlined", type: "delete" }}
                      aria-label={t("chatbot.sessionAttachments.deleteAria", { name: attachment.name })}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(attachment.attachmentId);
                      }}
                    />
                  </span>
                </button>
              );
            })
          )}
        </div>
      </InlineDrawer>
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
