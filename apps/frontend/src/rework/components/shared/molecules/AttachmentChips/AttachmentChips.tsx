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

import type { ChatAttachment } from "@rework/types/attachments";
import Chip from "@shared/atoms/Chip/Chip";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { fileIconSpec } from "../../../../utils/fileIconSpec";
import styles from "./AttachmentChips.module.css";

interface AttachmentChipsProps {
  attachments: ChatAttachment[];
  onRemove: (id: string) => void;
  onRetry?: (id: string, file: File) => void;
  onOpen?: (id: string) => void;
  /** One full-width chip per line instead of a horizontal row. */
  stacked?: boolean;
}

function fileLabel(attachment: ChatAttachment, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (attachment.status === "uploading")
    return t(attachment.canRetry ? "rework.documentStorage.uncertain" : "chatbot.attachmentChip.uploading");
  if (attachment.status === "error")
    return t(`chatbot.attachmentChip.failedReason.${attachment.error}`, {
      defaultValue: t("chatbot.attachmentChip.failed"),
    });
  if (attachment.status === "ingesting") return t("chatbot.attachmentChip.processing");
  return t("chatbot.attachmentChip.ready");
}

export function AttachmentChips({ attachments, onRemove, onRetry, onOpen, stacked }: AttachmentChipsProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const retryInput = useRef<HTMLInputElement>(null);
  const retryId = useRef<string | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth) return; // nothing to scroll horizontally
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return; // gesture already horizontal
      el.scrollLeft += e.deltaY;
      e.preventDefault();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [attachments.length]);

  if (attachments.length === 0) return null;

  return (
    <div
      ref={scrollRef}
      className={styles.chips}
      data-stacked={stacked}
      aria-label={t("chatbot.attachmentChip.ariaLabel")}
    >
      <input
        type="file"
        hidden
        ref={retryInput}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file && retryId.current) onRetry?.(retryId.current, file);
          event.target.value = "";
        }}
      />
      {attachments.map((attachment) => (
        <Chip
          key={attachment.id}
          tone={attachment.status === "error" ? "error" : attachment.status === "ready" ? "success" : "tertiary"}
          leading={
            <span className={styles.fileIcon}>
              <Icon category="outlined" type={fileIconSpec(attachment.name, attachment.mime).type} />
            </span>
          }
          label={attachment.name}
          title={
            attachment.error
              ? `${attachment.name}: ${t(`chatbot.attachments.errors.${attachment.error}`, { defaultValue: t("chatbot.attachments.processingUnavailable") })}`
              : attachment.name
          }
          secondary={[fileLabel(attachment, t), attachment.detail].filter(Boolean).join(" · ")}
          onClick={onOpen && (() => onOpen(attachment.id))}
          trailing={
            attachment.canRetry && onRetry ? (
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "refresh" }}
                aria-label={t("chatbot.attachments.retryUpload")}
                onClick={() => {
                  retryId.current = attachment.id;
                  retryInput.current?.click();
                }}
              />
            ) : undefined
          }
          onRemove={attachment.canRemove === false ? undefined : () => onRemove(attachment.id)}
          removeButtonSize="small"
          removeIcon={attachment.status === "ready" || attachment.status === "error" ? "delete" : "close"}
          removeAriaLabel={t("chatbot.attachmentChip.removeAria", { name: attachment.name })}
        />
      ))}
    </div>
  );
}
