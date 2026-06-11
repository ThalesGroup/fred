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
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { InlineDrawer } from "../InlineDrawer/InlineDrawer";
import { MarkdownRenderer } from "../MarkdownRenderer/MarkdownRenderer";
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
  const [selectedAttachmentId, setSelectedAttachmentId] = useState<string | null>(null);

  useEffect(() => {
    if (attachments.length === 0) {
      setSelectedAttachmentId(null);
      return;
    }
    if (!selectedAttachmentId || !attachments.some((attachment) => attachment.attachmentId === selectedAttachmentId)) {
      setSelectedAttachmentId(attachments[0].attachmentId);
    }
  }, [attachments, selectedAttachmentId]);

  const selected = useMemo(
    () => attachments.find((attachment) => attachment.attachmentId === selectedAttachmentId) ?? null,
    [attachments, selectedAttachmentId],
  );

  return (
    <InlineDrawer open={open} onClose={onClose} title="Conversation files" width="620px">
      <div className={styles.layout}>
        <div className={styles.list}>
          {isLoading && attachments.length === 0 ? (
            <div className={styles.empty}>Loading files…</div>
          ) : attachments.length === 0 ? (
            <div className={styles.empty}>No files attached to this conversation.</div>
          ) : (
            attachments.map((attachment) => {
              const sizeLabel = formatBytes(attachment.sizeBytes);
              const timestampLabel = formatTimestamp(attachment.createdAt);
              return (
                <button
                  key={attachment.attachmentId}
                  type="button"
                  className={styles.row}
                  data-selected={attachment.attachmentId === selectedAttachmentId}
                  onClick={() => setSelectedAttachmentId(attachment.attachmentId)}
                >
                  <span className={styles.rowIcon} aria-hidden>
                    <Icon category="outlined" type="attach_file" />
                  </span>
                  <span className={styles.rowBody}>
                    <span className={styles.rowName} title={attachment.name}>
                      {attachment.name}
                    </span>
                    <span className={styles.rowMeta}>
                      {[attachment.mime, sizeLabel, timestampLabel].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <IconButton
                    color="on-surface"
                    variant="icon"
                    size="xs"
                    icon={{ category: "outlined", type: "delete" }}
                    aria-label={`Delete ${attachment.name}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onDelete(attachment.attachmentId);
                    }}
                  />
                </button>
              );
            })
          )}
        </div>
        <div className={styles.preview}>
          {selected ? (
            <MarkdownRenderer text={selected.summaryMd || "_(No summary returned by Knowledge Flow)_"} />
          ) : (
            <div className={styles.empty}>Select a file to preview its markdown summary.</div>
          )}
        </div>
      </div>
    </InlineDrawer>
  );
}
