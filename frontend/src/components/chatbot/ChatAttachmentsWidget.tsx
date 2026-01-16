// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import AttachFileIcon from "@mui/icons-material/AttachFile";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import {
  Badge,
  Box,
  Button,
  ClickAwayListener,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Paper,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation,
  useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery,
} from "../../slices/agentic/agenticOpenApi";

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
  onAddAttachments,
  onAttachmentsUpdated,
  onOpen,
  onClose,
}: ChatAttachmentsWidgetProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [fetchSummary, { isFetching: isSummaryFetching }] =
    useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery();
  const [deleteAttachment, { isLoading: isDeleting }] = useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation();
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryTitle, setSummaryTitle] = useState("");
  const [summaryText, setSummaryText] = useState("");
  const isVisible = open;
  const count = attachments.length;

  const widgetBody = (
    <Paper
      elevation={2}
      sx={{
        width: "100%",
        minWidth: "100%",
        maxWidth: "100%",
        maxHeight: "70vh",
        borderRadius: 3,
        border: `1px solid ${theme.palette.divider}`,
        p: 1.5,
        bgcolor: theme.palette.background.paper,
      }}
    >
      <Stack spacing={1} sx={{ pb: 0.5 }}>
        <Box display="flex" alignItems="center" gap={1} sx={{ width: "100%" }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Button
              variant="outlined"
              size="small"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              sx={{
                borderRadius: "8px",
                textTransform: "none",
                minHeight: 28,
                overflow: "hidden",
                px: 1.5,
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {t("chatbot.attachFiles", "Attach files")}
            </Button>
          </Box>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box>
          {count > 0 ? (
            <List
              dense
              disablePadding
              sx={{
                maxHeight: "40vh",
                overflowY: "auto",
                "&::-webkit-scrollbar": { width: 6 },
                "&::-webkit-scrollbar-thumb": {
                  backgroundColor: theme.palette.divider,
                  borderRadius: 4,
                },
              }}
            >
              {attachments.map((item) => (
                <ListItem
                  key={item.id}
                  disableGutters
                  secondaryAction={
                    <Stack direction="row" spacing={0.5}>
                      <IconButton
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
                              typeof data === "string"
                                ? data
                                : (data?.summary ?? data?.content ?? JSON.stringify(data));
                            setSummaryText(text || "No summary available.");
                          } catch {
                            setSummaryText("No summary available.");
                          }
                        }}
                      >
                        <VisibilityOutlinedIcon fontSize="small" />
                      </IconButton>
                      <IconButton
                        size="small"
                        disabled={disabled || isDeleting || !sessionId}
                        onClick={async () => {
                          if (!sessionId) return;
                          await deleteAttachment({ attachmentId: item.id, sessionId })
                            .unwrap()
                            .catch(() => undefined);
                          onAttachmentsUpdated?.();
                        }}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Stack>
                  }
                  sx={{ pr: 4 }}
                >
                  <ListItemText primary={item.name} primaryTypographyProps={{ variant: "body2", noWrap: true }} />
                </ListItem>
              ))}
            </List>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ pb: 0.5 }}>
              {t("chatbot.attachments.noAttachments", "No attachments yet")}
            </Typography>
          )}
        </Box>
      </Stack>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        accept=".pdf,.docx,.csv"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) onAddAttachments?.(files);
          event.target.value = "";
        }}
      />
    </Paper>
  );

  return (
    <Box sx={{ position: "relative", width: isVisible ? "100%" : "auto" }}>
      {!isVisible && (
        <IconButton
          size="small"
          onClick={onOpen}
          aria-label={t("chatbot.attachments.drawerTitle", "Attachments")}
          disabled={disabled}
          sx={{ color: disabled ? "text.disabled" : "inherit" }}
        >
          <Badge
            color={disabled ? "default" : "primary"}
            badgeContent={count > 0 ? count : undefined}
            overlap="circular"
            anchorOrigin={{ vertical: "top", horizontal: "right" }}
            sx={{ "& .MuiBadge-badge": { opacity: disabled ? 0.5 : 1 } }}
          >
            <AttachFileIcon fontSize="small" />
          </Badge>
        </IconButton>
      )}

      {isVisible && closeOnClickAway && (
        <ClickAwayListener onClickAway={onClose}>
          <Box sx={{ width: "100%" }}>{widgetBody}</Box>
        </ClickAwayListener>
      )}
      {isVisible && !closeOnClickAway && <Box sx={{ width: "100%" }}>{widgetBody}</Box>}
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
    </Box>
  );
};

export default ChatAttachmentsWidget;
