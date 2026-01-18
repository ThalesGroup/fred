// Copyright Thales 2025
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

import AttachFileIcon from "@mui/icons-material/AttachFile";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import MicIcon from "@mui/icons-material/Mic";
import UploadIcon from "@mui/icons-material/Upload";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation,
  useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery,
} from "../../../slices/agentic/agenticOpenApi.ts";
import MarkdownRenderer from "../../markdown/MarkdownRenderer.tsx";

interface AttachmentRef {
  id: string;
  name: string;
}

interface UserInputAttachmentsProps {
  sessionId?: string;
  sessionAttachments: AttachmentRef[];
  files: File[] | null;
  uploadingFileNames?: string[];
  audio: Blob | null;
  open: boolean;
  uploadDialogOpen: boolean;
  onToggleOpen: (open: boolean) => void;
  onOpenUploadDialog: () => void;
  onCloseUploadDialog: () => void;
  onFilesDropped?: (files: File[]) => void;
  onRemoveFile: (index: number) => void;
  onShowAudioController: () => void;
  onRemoveAudio: () => void;
  onAttachFileClick: () => void;
  onRefreshSessionAttachments?: () => void;
}

export const UserInputAttachments: React.FC<UserInputAttachmentsProps> = ({
  sessionId,
  sessionAttachments,
  files,
  uploadingFileNames,
  audio,
  open,
  uploadDialogOpen,
  onToggleOpen,
  onOpenUploadDialog,
  onCloseUploadDialog,
  onFilesDropped,
  onRemoveFile,
  onShowAudioController,
  onRemoveAudio,
  onAttachFileClick,
  onRefreshSessionAttachments,
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDarkTheme = theme.palette.mode === "dark";
  const [deleteAttachment, { isLoading: isDeleting }] = useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation();
  const [fetchSummary, { data: summaryData, isFetching: isFetchingSummary, error: summaryError }] =
    useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery();
  const [previewingAttachmentId, setPreviewingAttachmentId] = useState<string | null>(null);
  const [previewingAttachmentName, setPreviewingAttachmentName] = useState<string>("");

  const localFilesCount = files?.length ?? 0;
  const attachmentCount = sessionAttachments.length + (uploadingFileNames?.length ?? 0) + localFilesCount;
  const hasContent = attachmentCount > 0 || !!audio;

  const handleDeleteAttachment = async (attachmentId: string) => {
    if (!sessionId) return;
    try {
      await deleteAttachment({ attachmentId, sessionId }).unwrap();
      onRefreshSessionAttachments?.();
    } catch (e) {
      console.error("Failed to delete attachment", attachmentId, e);
    }
  };

  const handlePreviewAttachment = (attachmentId: string, name: string) => {
    const sid = sessionId;
    if (!sid) return;
    setPreviewingAttachmentId(attachmentId);
    setPreviewingAttachmentName(name);
    fetchSummary({ sessionId: sid, attachmentId });
  };

  const panelWidth = open ? { xs: "min(92vw, 320px)", sm: 340 } : 0;

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const droppedFiles = Array.from(event.dataTransfer?.files || []);
    if (droppedFiles.length) {
      onFilesDropped?.(droppedFiles);
      onCloseUploadDialog();
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  return (
    <>
      <Box
        sx={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          height: "100vh",
          flexShrink: 0,
          width: panelWidth,
          transition: "width 240ms ease",
          display: "flex",
          flexDirection: "column",
          borderLeft: open ? `1px solid ${theme.palette.divider}` : "none",
          background: theme.palette.background.paper,
          boxShadow: open ? theme.shadows[3] : "none",
          zIndex: theme.zIndex.drawer,
          overflow: "hidden",
          pointerEvents: open ? "auto" : "none",
        }}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ p: open ? 1.5 : 1 }}>
          <Stack
            direction="row"
            alignItems="center"
            spacing={open ? 1 : 0}
            sx={{ cursor: open ? "default" : "pointer" }}
            onClick={() => {
              if (!open) onToggleOpen(true);
            }}
          >
            {open && (
              <Box>
                <Typography variant="subtitle2">{t("chatbot.attachments.drawerTitle")}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {t("chatbot.attachments.count", { count: attachmentCount })}
                </Typography>
              </Box>
            )}
          </Stack>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <Tooltip title={t("chatbot.attachFiles")}>
              <span>
                <IconButton
                  size="small"
                  onClick={() => {
                    if (!open) onToggleOpen(true);
                    onOpenUploadDialog();
                  }}
                >
                  <AttachFileIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <IconButton size="small" onClick={() => onToggleOpen(!open)}>
              {open ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
            </IconButton>
          </Stack>
        </Stack>

        {open ? (
          <Stack
            spacing={1.25}
            sx={{
              flex: 1,
              px: 1.5,
              pb: 2,
              overflowY: "auto",
              "&::-webkit-scrollbar": { width: "5px" },
              "&::-webkit-scrollbar-thumb": {
                backgroundColor: isDarkTheme ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)",
                borderRadius: "3px",
              },
            }}
          >
            {!hasContent && (
              <Typography variant="body2" color="text.secondary" textAlign="center">
                {t("chatbot.attachments.noAttachments")}
              </Typography>
            )}

            {uploadingFileNames && uploadingFileNames.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
                  {t("common.uploading")}
                </Typography>
                <Stack spacing={0.75}>
                  {uploadingFileNames.map((name, i) => (
                    <Box
                      key={`${name}-${i}-uploading`}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        p: 1,
                        borderRadius: 1,
                        backgroundColor: theme.palette.action.hover,
                      }}
                    >
                      <CircularProgress size={18} />
                      <Typography variant="body2">
                        {t("chatbot.uploadingFile", {
                          defaultValue: "Uploading {{name}}...",
                          name,
                        })}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            {sessionAttachments.length > 0 && (
              <Box>
                <Stack spacing={0.75}>
                  {sessionAttachments.map((att) => (
                    <Box
                      key={att.id}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        p: 1,
                        borderRadius: 1,
                        border: `1px solid ${theme.palette.divider}`,
                      }}
                    >
                      <Stack direction="row" alignItems="center" spacing={1} sx={{ flex: 1, minWidth: 0 }}>
                        <AttachFileIcon fontSize="small" />
                        <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                          {att.name}
                        </Typography>
                      </Stack>
                      <Tooltip
                        title={
                          sessionId
                            ? t("common.preview")
                            : t("chatbot.attachments.noSession", "Start a session to preview")
                        }
                      >
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => handlePreviewAttachment(att.id, att.name)}
                            disabled={!sessionId || (isFetchingSummary && previewingAttachmentId === att.id)}
                          >
                            <VisibilityOutlinedIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title={t("common.remove")}>
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => handleDeleteAttachment(att.id)}
                            disabled={isDeleting || !sessionId}
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            {files && files.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
                  {t("chatbot.attachments.pending", "Pending attachments")}
                </Typography>
                <Stack spacing={0.75}>
                  {files.map((f, i) => (
                    <Box
                      key={`${f.name}-${i}`}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        p: 1,
                        borderRadius: 1,
                        border: `1px dashed ${theme.palette.divider}`,
                      }}
                    >
                      <Stack direction="row" alignItems="center" spacing={1} sx={{ flex: 1, minWidth: 0 }}>
                        <AttachFileIcon fontSize="small" />
                        <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                          {f.name.replace(/\.[^/.]+$/, "")}
                        </Typography>
                      </Stack>
                      <Tooltip title={t("common.remove")}>
                        <IconButton size="small" onClick={() => onRemoveFile(i)}>
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            {audio && (
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
                  {t("chatbot.attachments.audio", "Audio")}
                </Typography>
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    p: 1,
                    borderRadius: 1,
                    border: `1px dashed ${theme.palette.divider}`,
                  }}
                >
                  <Stack direction="row" alignItems="center" spacing={1} sx={{ flex: 1 }}>
                    <MicIcon fontSize="small" color="error" />
                    <Typography variant="body2">{t("chatbot.audioChip", "Audio recording")}</Typography>
                  </Stack>
                  <Stack direction="row" alignItems="center" spacing={0.5}>
                    <Button
                      size="small"
                      onClick={onShowAudioController}
                      startIcon={<VisibilityIcon fontSize="small" />}
                    >
                      {t("chatbot.attachments.play", "Show")}
                    </Button>
                    <Tooltip title={t("common.remove")}>
                      <IconButton size="small" onClick={onRemoveAudio}>
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Box>
              </Box>
            )}
          </Stack>
        ) : (
          <Stack alignItems="center" spacing={1} sx={{ flex: 1, justifyContent: "flex-start", py: 1 }}>
            <Tooltip title={t("chatbot.attachFiles")}>
              <IconButton
                size="small"
                onClick={() => {
                  onToggleOpen(true);
                  onOpenUploadDialog();
                }}
              >
                <UploadIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        )}
      </Box>

      <Dialog
        open={Boolean(previewingAttachmentId)}
        onClose={() => setPreviewingAttachmentId(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 1 }}>
          <Typography variant="subtitle1" noWrap sx={{ pr: 1 }}>
            {previewingAttachmentName || t("chatbot.attachments.previewTitle", "Attachment preview")}
          </Typography>
          <Stack direction="row" alignItems="center" spacing={1}>
            {isFetchingSummary && <CircularProgress size={18} />}
            <IconButton size="small" onClick={() => setPreviewingAttachmentId(null)}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </DialogTitle>
        <DialogContent dividers>
          {summaryError ? (
            <Typography variant="body2" color="error">
              {t("common.loadingPreviewError")}
            </Typography>
          ) : isFetchingSummary && summaryData?.attachment_id !== previewingAttachmentId ? (
            <Typography variant="body2" color="text.secondary">
              {t("common.loadingPreview")}
            </Typography>
          ) : (
            <MarkdownRenderer
              content={summaryData?.attachment_id === previewingAttachmentId ? summaryData.summary_md || "" : ""}
              size="medium"
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={uploadDialogOpen} onClose={onCloseUploadDialog} fullWidth maxWidth="sm">
        <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 1 }}>
          <Typography variant="subtitle1" noWrap sx={{ pr: 1 }}>
            {t("chatbot.attachFiles")}
          </Typography>
          <IconButton size="small" onClick={onCloseUploadDialog}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Paper
            variant="outlined"
            sx={{
              p: 3,
              borderStyle: "dashed",
              borderColor: "divider",
              borderRadius: 2,
              cursor: "pointer",
              textAlign: "center",
              backgroundColor: theme.palette.action.hover,
              "&:hover": {
                backgroundColor: theme.palette.action.selected,
              },
            }}
            onClick={() => {
              onAttachFileClick();
            }}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
          >
            <UploadIcon sx={{ fontSize: 36, color: "text.secondary", mb: 1 }} />
            <Typography variant="body1" sx={{ fontWeight: 600 }}>
              {t("common.dropHere")}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t("chatbot.attachments.supportedFormats")}
            </Typography>
          </Paper>
        </DialogContent>
      </Dialog>
    </>
  );
};
