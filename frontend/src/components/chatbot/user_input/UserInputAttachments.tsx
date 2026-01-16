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

import AddIcon from "@mui/icons-material/Add";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import MicIcon from "@mui/icons-material/Mic";
import UploadIcon from "@mui/icons-material/Upload";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import {
  Box,
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
import { ChatDocumentLibrariesSelectionCard } from "../ChatDocumentLibrariesSelectionCard.tsx";
import { ChatResourcesSelectionCard } from "../ChatResourcesSelectionCard.tsx";
import { ConversationItemList } from "../ConversationItemList.tsx";

interface AttachmentRef {
  id: string;
  name: string;
}

export type ConversationPanelView = "chat_contexts" | "libraries" | "attachments";

interface UserInputAttachmentsProps {
  sessionId?: string;
  sessionAttachments: AttachmentRef[];
  files: File[] | null;
  uploadingFileNames?: string[];
  audio: Blob | null;
  open: boolean;
  view: ConversationPanelView;
  attachmentsActionsEnabled?: boolean;
  librariesActionsEnabled?: boolean;
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
  selectedChatContextIds?: string[];
  chatContextNameById?: Record<string, string>;
  onSelectedChatContextIdsChange?: (ids: string[]) => void;
  selectedDocumentLibrariesIds?: string[];
  documentLibraryNameById?: Record<string, string>;
  onSelectedDocumentLibrariesIdsChange?: (next: React.SetStateAction<string[]>) => void;
}

export const UserInputAttachments: React.FC<UserInputAttachmentsProps> = ({
  sessionId,
  sessionAttachments,
  files,
  uploadingFileNames,
  audio,
  open,
  view,
  attachmentsActionsEnabled = true,
  librariesActionsEnabled = true,
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
  selectedChatContextIds,
  chatContextNameById,
  onSelectedChatContextIdsChange,
  selectedDocumentLibrariesIds,
  documentLibraryNameById,
  onSelectedDocumentLibrariesIdsChange,
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDarkTheme = theme.palette.mode === "dark";
  const [deleteAttachment, { isLoading: isDeleting }] = useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation();
  const [fetchSummary, { data: summaryData, isFetching: isFetchingSummary, error: summaryError }] =
    useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery();
  const [previewingAttachmentId, setPreviewingAttachmentId] = useState<string | null>(null);
  const [previewingAttachmentName, setPreviewingAttachmentName] = useState<string>("");
  const [chatContextsDialogOpen, setChatContextsDialogOpen] = useState<boolean>(false);
  const [librariesDialogOpen, setLibrariesDialogOpen] = useState<boolean>(false);

  const localFilesCount = files?.length ?? 0;
  const attachmentCount = sessionAttachments.length + (uploadingFileNames?.length ?? 0) + localFilesCount;
  const attachmentsTotalCount = attachmentCount + (audio ? 1 : 0);
  const chatContextIds = selectedChatContextIds ?? [];
  const documentLibraryIds = selectedDocumentLibrariesIds ?? [];

  const addActionDisabled =
    (view === "attachments" && !attachmentsActionsEnabled) ||
    (view === "libraries" && (!librariesActionsEnabled || !onSelectedDocumentLibrariesIdsChange)) ||
    (view === "chat_contexts" && !onSelectedChatContextIdsChange);

  const handleAddAction = () => {
    if (addActionDisabled) return;
    if (!open) onToggleOpen(true);
    if (view === "attachments") {
      onOpenUploadDialog();
    } else if (view === "libraries") {
      setLibrariesDialogOpen(true);
    } else {
      setChatContextsDialogOpen(true);
    }
  };

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
          background: theme.palette.surfaces?.soft
            ? theme.palette.surfaces.soft
            : (theme.palette.sidebar?.background ?? theme.palette.background.paper),
          boxShadow: open ? theme.shadows[3] : "none",
          zIndex: theme.zIndex.drawer,
          overflow: "hidden",
          pointerEvents: open ? "auto" : "none",
        }}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ p: open ? 1.5 : 1 }}>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <Tooltip
              title={
                view === "attachments"
                  ? t("chatbot.attachFiles")
                  : view === "libraries"
                    ? t("common.add")
                    : t("common.add")
              }
            >
              <span>
                <IconButton
                  size="small"
                  disabled={addActionDisabled}
                  onClick={handleAddAction}
                  sx={addActionDisabled ? { opacity: 0.45 } : undefined}
                >
                  <AddIcon fontSize="small" />
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
            {view === "chat_contexts" ? (
              <ConversationItemList
                title={t("settings.chatContext", "Chat Context")}
                count={chatContextIds.length}
                emptyText={t("common.noneSelected")}
                headerActions={
                  <Tooltip title={t("documentLibrary.clearSelection")}>
                    <span>
                      <IconButton
                        size="small"
                        disabled={!chatContextIds.length || !onSelectedChatContextIdsChange}
                        onClick={() => onSelectedChatContextIdsChange?.([])}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                }
                items={chatContextIds.map((id) => ({
                  key: id,
                  primary: chatContextNameById?.[id] ?? id,
                  startAdornment: <ForumOutlinedIcon fontSize="small" />,
                  onClick: onSelectedChatContextIdsChange ? () => setChatContextsDialogOpen(true) : undefined,
                  endAdornment: (
                    <Tooltip title={t("common.remove")}>
                      <span>
                        <IconButton
                          size="small"
                          disabled={!onSelectedChatContextIdsChange}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectedChatContextIdsChange?.(chatContextIds.filter((x) => x !== id));
                          }}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  ),
                }))}
              />
            ) : null}

            {view === "libraries" ? (
              <ConversationItemList
                title={t("knowledge.viewSelector.libraries", "Libraries")}
                count={documentLibraryIds.length}
                emptyText={t("common.noneSelected")}
                headerActions={
                  <Tooltip title={t("documentLibrary.clearSelection")}>
                    <span>
                      <IconButton
                        size="small"
                        disabled={
                          !documentLibraryIds.length ||
                          !onSelectedDocumentLibrariesIdsChange ||
                          !librariesActionsEnabled
                        }
                        onClick={() => onSelectedDocumentLibrariesIdsChange?.([])}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                }
                items={documentLibraryIds.map((id) => ({
                  key: id,
                  primary: documentLibraryNameById?.[id] ?? id,
                  startAdornment: <LibraryBooksIcon fontSize="small" />,
                  onClick:
                    onSelectedDocumentLibrariesIdsChange && librariesActionsEnabled
                      ? () => setLibrariesDialogOpen(true)
                      : undefined,
                  endAdornment: (
                    <Tooltip title={t("common.remove")}>
                      <span>
                        <IconButton
                          size="small"
                          disabled={!onSelectedDocumentLibrariesIdsChange || !librariesActionsEnabled}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectedDocumentLibrariesIdsChange?.(documentLibraryIds.filter((x) => x !== id));
                          }}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  ),
                }))}
              />
            ) : null}

            {view === "attachments" ? (
              <ConversationItemList
                title={t("chatbot.attachments.drawerTitle", "Attachments")}
                count={attachmentsTotalCount}
                emptyText={t("chatbot.attachments.noAttachments")}
                items={[
                  ...(uploadingFileNames?.map((name, i) => ({
                    key: `${name}-${i}-uploading`,
                    primary: t("chatbot.uploadingFile", {
                      defaultValue: "Uploading {{name}}...",
                      name,
                    }),
                    startAdornment: <CircularProgress size={18} />,
                  })) ?? []),
                  ...sessionAttachments.map((att) => ({
                    key: `session-${att.id}`,
                    primary: att.name,
                    startAdornment: <AttachFileIcon fontSize="small" />,
                    onClick:
                      sessionId && !(isFetchingSummary && previewingAttachmentId === att.id)
                        ? () => handlePreviewAttachment(att.id, att.name)
                        : undefined,
                    endAdornment: (
                      <Stack direction="row" alignItems="center" spacing={0.25}>
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
                              onClick={(e) => {
                                e.stopPropagation();
                                handlePreviewAttachment(att.id, att.name);
                              }}
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
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteAttachment(att.id);
                              }}
                              disabled={isDeleting || !sessionId}
                            >
                              <DeleteOutlineIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    ),
                  })),
                  ...(files?.map((f, i) => ({
                    key: `${f.name}-${i}-pending`,
                    primary: f.name,
                    secondary: t("chatbot.attachments.pending", "Pending attachments"),
                    startAdornment: <AttachFileIcon fontSize="small" />,
                    endAdornment: (
                      <Tooltip title={t("common.remove")}>
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemoveFile(i);
                          }}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    ),
                  })) ?? []),
                  ...(audio
                    ? [
                        {
                          key: "audio",
                          primary: t("chatbot.audioChip", "Audio recording"),
                          startAdornment: <MicIcon fontSize="small" color="error" />,
                          endAdornment: (
                            <Stack direction="row" alignItems="center" spacing={0.25}>
                              <Tooltip title={t("chatbot.attachments.play", "Show")}>
                                <IconButton
                                  size="small"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onShowAudioController();
                                  }}
                                >
                                  <VisibilityIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title={t("common.remove")}>
                                <IconButton
                                  size="small"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onRemoveAudio();
                                  }}
                                >
                                  <DeleteOutlineIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            </Stack>
                          ),
                        },
                      ]
                    : []),
                ]}
              />
            ) : null}
          </Stack>
        ) : (
          <Stack alignItems="center" spacing={1} sx={{ flex: 1, justifyContent: "flex-start", py: 1 }}>
            <Tooltip title={t("chatbot.attachFiles")}>
              <IconButton
                size="small"
                onClick={() => {
                  if (!attachmentsActionsEnabled) return;
                  onToggleOpen(true);
                  onOpenUploadDialog();
                }}
                disabled={!attachmentsActionsEnabled}
                sx={!attachmentsActionsEnabled ? { opacity: 0.45 } : undefined}
              >
                <UploadIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        )}
      </Box>

      <Dialog
        open={chatContextsDialogOpen}
        onClose={() => setChatContextsDialogOpen(false)}
        PaperProps={{ sx: { width: { xs: "min(90vw, 460px)", sm: "min(500px, 80vw)" } } }}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 1 }}>
          <Typography variant="subtitle1" noWrap sx={{ pr: 1 }}>
            {t("settings.chatContext", "Chat Context")}
          </Typography>
          <IconButton size="small" onClick={() => setChatContextsDialogOpen(false)}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0, pb: 1 }}>
          <ChatResourcesSelectionCard
            libraryType={"chat-context"}
            selectedResourceIds={chatContextIds}
            setSelectedResourceIds={(ids) => onSelectedChatContextIdsChange?.(ids)}
            selectionMode="multiple"
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={librariesDialogOpen}
        onClose={() => setLibrariesDialogOpen(false)}
        PaperProps={{ sx: { width: { xs: "min(90vw, 460px)", sm: "min(500px, 80vw)" } } }}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 1 }}>
          <Typography variant="subtitle1" noWrap sx={{ pr: 1 }}>
            {t("knowledge.viewSelector.libraries", "Libraries")}
          </Typography>
          <IconButton size="small" onClick={() => setLibrariesDialogOpen(false)}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0, pb: 1 }}>
          <ChatDocumentLibrariesSelectionCard
            selectedLibrariesIds={documentLibraryIds}
            setSelectedLibrariesIds={onSelectedDocumentLibrariesIdsChange ?? ((_: string[]) => {})}
            libraryType="document"
          />
        </DialogContent>
      </Dialog>

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
              cursor: attachmentsActionsEnabled ? "pointer" : "default",
              textAlign: "center",
              backgroundColor: theme.palette.action.hover,
              "&:hover": {
                backgroundColor: attachmentsActionsEnabled ? theme.palette.action.selected : theme.palette.action.hover,
              },
              opacity: attachmentsActionsEnabled ? 1 : 0.6,
            }}
            onClick={() => {
              if (!attachmentsActionsEnabled) return;
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
