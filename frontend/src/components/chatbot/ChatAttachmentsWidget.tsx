// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import AttachFileIcon from "@mui/icons-material/AttachFile";
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation,
  useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery,
} from "../../slices/agentic/agenticOpenApi";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";
import { LoadingIcon } from "../../shared/ui/buttons/LoadingIcon";
import { ViewIconButton } from "../../shared/ui/buttons/ViewIconButton";
import ChatWidgetList from "./ChatWidgetList.tsx";
import ChatWidgetShell from "./ChatWidgetShell.tsx";

export type ChatAttachmentItem = {
  id: string;
  name: string;
};

export type ChatAttachmentsWidgetProps = {
  attachments: ChatAttachmentItem[];
  sessionId?: string;
  open: boolean;
  closeOnClickAway?: boolean;
  disabled?: boolean;
  isUploading?: boolean;
  onAddAttachments?: (files: File[]) => void;
  onAttachmentsUpdated?: () => void;
  onOpen: () => void;
  onClose: () => void;
};

const ChatAttachmentsWidget = ({
  attachments,
  sessionId,
  open,
  closeOnClickAway = true,
  disabled = false,
  isUploading = false,
  onAddAttachments,
  onAttachmentsUpdated,
  onOpen,
  onClose,
}: ChatAttachmentsWidgetProps) => {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [fetchSummary, { isFetching: isSummaryFetching }] =
    useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery();
  const [deleteAttachment, { isLoading: isDeleting }] = useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation();
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryTitle, setSummaryTitle] = useState("");
  const [summaryText, setSummaryText] = useState("");
  const count = attachments.length;
  const items = attachments.map((item) => ({
    id: item.id,
    label: item.name,
    secondaryAction: (
      <Stack direction="row" spacing={0.5}>
        <ViewIconButton
          size="small"
          disabled={disabled || !sessionId}
          onClick={async () => {
            if (!sessionId) return;
            setSummaryTitle(item.name);
            setSummaryText("");
            setSummaryOpen(true);
            try {
              const data = await fetchSummary({ attachmentId: item.id, sessionId }).unwrap();
              const text =
                typeof data === "string" ? data : (data?.summary ?? data?.content ?? JSON.stringify(data));
              setSummaryText(text || "No summary available.");
            } catch {
              setSummaryText("No summary available.");
            }
          }}
        />
        <DeleteIconButton
          size="small"
          disabled={disabled || isDeleting || !sessionId}
          onClick={async () => {
            if (!sessionId) return;
            await deleteAttachment({ attachmentId: item.id, sessionId })
              .unwrap()
              .catch(() => undefined);
            onAttachmentsUpdated?.();
          }}
        />
      </Stack>
    ),
  }));

  return (
    <>
      <ChatWidgetShell
        open={open}
        onOpen={onOpen}
        onClose={onClose}
        closeOnClickAway={closeOnClickAway}
        disabled={disabled}
        badgeCount={count}
        icon={<AttachFileIcon fontSize="small" />}
        ariaLabel={t("chatbot.attachments.drawerTitle", "Attachments")}
        tooltipLabel={t("chatbot.attachments.drawerTitle", "Attachments")}
        tooltipDescription={t(
          "chatbot.attachments.tooltip.description",
          "Files attached to this conversation.",
        )}
        tooltipDisabledReason={
          disabled ? t("chatbot.attachments.tooltip.disabled", "This agent does not use attachments.") : undefined
        }
        actionLabel={
          isUploading ? t("common.uploading", "Uploading...") : t("chatbot.attachFiles", "Attach files")
        }
        actionStartIcon={isUploading ? <LoadingIcon size={14} /> : undefined}
        actionDisabled={disabled || isUploading}
        onAction={() => fileInputRef.current?.click()}
      >
        <ChatWidgetList items={items} emptyText={t("chatbot.attachments.noAttachments", "No attachments yet")} />
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            if (files.length) onAddAttachments?.(files);
            event.target.value = "";
          }}
        />
      </ChatWidgetShell>
      <Dialog open={summaryOpen} onClose={() => setSummaryOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{summaryTitle || t("chatbot.attachments.drawerTitle", "Attachments")}</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary">
            {isSummaryFetching ? t("common.loading", "Loading…") : summaryText || "No summary available."}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSummaryOpen(false)}>{t("common.close", "Close")}</Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default ChatAttachmentsWidget;
