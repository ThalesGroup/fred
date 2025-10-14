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

import CloseIcon from "@mui/icons-material/Close";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DeleteIcon from "@mui/icons-material/Delete";
import FilePresentIcon from "@mui/icons-material/FilePresent"; // New icon for file list
import UploadIcon from "@mui/icons-material/Upload";
import {
  Box,
  Button,
  CircularProgress,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Paper, // New import
  Typography,
  useTheme,
} from "@mui/material";
import React, { useMemo, useState } from "react";
import { useDropzone } from "react-dropzone"; // New import

import { useTranslation } from "react-i18next";

// --- RTK Query Hooks & Types ---
import {
  AssetMeta,
  useDeleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteMutation,
  useListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetQuery,
  useUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPostMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";
import { useToast } from "../ToastProvider";
// -------------------------------

interface AgentAssetManagerDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  agentId: string; // The ID of the agent whose assets we manage
}

// Helper to format file size
const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};

export const AgentAssetManagerDrawer: React.FC<AgentAssetManagerDrawerProps> = ({ isOpen, onClose, agentId }) => {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const theme = useTheme();

  // --- State for Upload Form (Modified) ---
  const [filesToUpload, setFilesToUpload] = useState<File[]>([]); // List of files ready to upload
  const [isHighlighted, setIsHighlighted] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false); // Used while iterating through files

  // --- RTK Query Initialization ---
  const {
    data: listData,
    isLoading: isListLoading,
    isFetching: isListFetching,
    refetch: refetchAssets,
  } = useListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetQuery(
    { agent: agentId },
    { skip: !isOpen }, // Skip query if drawer is closed
  );

  const [uploadAsset, { isLoading: isApiLoading }] =
    useUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPostMutation();

  const [deleteAsset] = useDeleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteMutation();
  // The overall loading state combines the API mutation state and the local processing loop state
  const isUploading = isApiLoading || isProcessing;
  // --------------------------------

  const assets: AssetMeta[] = useMemo(() => listData?.items || [], [listData]);

  // --- Dropzone Logic (Reused from DocumentUploadDrawer) ---
  const { getRootProps, getInputProps, open } = useDropzone({
    noKeyboard: true,
    onDrop: (acceptedFiles) => {
      setFilesToUpload((prevFiles) => {
        // Use a Set for efficient uniqueness check (by name and size)
        const existingIdentifiers = new Set(prevFiles.map((f) => `${f.name}-${f.size}`));

        const newUniqueFiles = acceptedFiles.filter((f) => !existingIdentifiers.has(`${f.name}-${f.size}`));

        if (newUniqueFiles.length < acceptedFiles.length) {
          showInfo({
            summary: t("assetManager.fileAlreadyAddedSummary") || "File Already Added",
            detail: t("assetManager.fileAlreadyAddedDetail") || "One or more files were already in the queue.",
          });
        }
        return [...prevFiles, ...newUniqueFiles];
      });
      setIsHighlighted(false);
    },
    // Prevent dropzone from opening file dialog on click by default
    // We will control it via the button
    noClick: true,
  });

  const handleDeleteTemp = (index: number) => {
    setFilesToUpload((prevFiles) => prevFiles.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (!filesToUpload.length) return;
    setIsProcessing(true); // Start processing loop

    const filesToProcess = [...filesToUpload];
    setFilesToUpload([]); // Clear queue immediately

    for (const file of filesToProcess) {
      // ⚠️ Use file.name as the key to maintain consistency with agent tuning
      const keyToUse = file.name;

      const formData = new FormData();
      formData.append("file", file);
      formData.append("key", keyToUse);
      // NOTE: ContentTypeOverride field is removed from UI and backend logic is relied upon

      try {
        await uploadAsset({
          agent: agentId,
          bodyUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPost: formData as any,
        }).unwrap();

        showInfo({
          summary: t("assetManager.uploadSuccessSummary") || "Asset Uploaded",
          detail:
            t("assetManager.uploadSuccessDetail", { key: keyToUse }) || `Asset '${keyToUse}' uploaded successfully.`,
        });
      } catch (err: any) {
        const errMsg = err?.data?.detail || err?.error || t("assetManager.unknownUploadError");
        console.error("Upload failed for file:", file.name, err);
        showError({
          summary: t("assetManager.uploadFailedSummary") || "Upload Failed",
          detail: `Failed to upload ${file.name}: ${errMsg}`,
        });
        // Important: Stop the loop on the first severe error or continue?
        // Continuing allows partial success, which is often preferable.
      }
    }

    setIsProcessing(false); // End processing loop
    refetchAssets();
  };

  const handleDelete = async (key: string) => {
    showConfirmationDialog({
      title: t("assetManager.confirmDeleteTitle") || "Confirm Deletion",
      message:
        t("assetManager.confirmDelete", { key }) ||
        `Are you sure you want to delete asset '${key}'? This action cannot be undone.`,
      onConfirm: async () => {
        try {
          await deleteAsset({ agent: agentId, key }).unwrap();
          showInfo({
            summary: t("assetManager.deleteSuccessSummary") || "Asset Deleted",
            detail: t("assetManager.deleteSuccessDetail", { key }) || `Asset '${key}' deleted.`,
          });
          refetchAssets();
        } catch (err: any) {
          const errMsg = err?.data?.detail || err?.error || t("assetManager.unknownDeleteError");
          console.error("Delete failed:", err);
          showError({ summary: t("assetManager.deleteFailedSummary") || "Deletion Failed", detail: errMsg });
        }
      },
    });
  };

  // Reset state on initial close
  const handleClose = () => {
    setFilesToUpload([]);
    setIsProcessing(false);
    onClose();
  };

  return (
    <Drawer
      anchor="right"
      open={isOpen}
      onClose={handleClose}
      slotProps={{
        paper: {
          sx: {
            width: { xs: "100%", sm: 500 },
            p: 3,
          },
        },
      }}
    >
      <Box display="flex" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight="bold">
          {t("assetManager.title", { agentId })}
        </Typography>
        <IconButton onClick={handleClose}>
          <CloseIcon />
        </IconButton>
      </Box>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        {t("assetManager.description")}
      </Typography>
      {/* --- 1. Asset Listing (Existing Assets) --- */}
      <Box sx={{ mt: 3, border: `1px solid ${theme.palette.divider}`, borderRadius: "8px", overflow: "hidden" }}>
        <Typography variant="subtitle1" sx={{ p: 2, bgcolor: theme.palette.action.hover }}>
          {t("assetManager.listTitle")}
          {(isListLoading || isListFetching) && <CircularProgress size={16} sx={{ ml: 1 }} />}
        </Typography>
        <Box sx={{ maxHeight: "30vh", overflowY: "auto" }}>
          <List dense disablePadding>
            {assets.length === 0 && !(isListLoading || isListFetching) ? (
              <ListItem>
                <ListItemText secondary={t("assetManager.noAssetsFound")} />
              </ListItem>
            ) : (
              assets.map((asset) => (
                <ListItem
                  key={asset.key}
                  // *** KEY CHANGE 1: Use flexbox for the entire ListItem ***
                  sx={{
                    py: 0.5,
                    px: 2,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderBottom: `1px solid ${theme.palette.divider}`,
                  }}
                  // *** KEY CHANGE 2: Removed secondaryAction prop ***
                >
                  {/* Name and Size container */}
                  <Box sx={{ flexGrow: 1, minWidth: 0, display: "flex", alignItems: "center" }}>
                    {/* File Name */}
                    <Typography
                      variant="body2"
                      fontWeight="medium"
                      component="span" // Ensure it renders inline
                      sx={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        // Takes up max space but respects other items
                        flexShrink: 1,
                        mr: 2,
                      }}
                    >
                      {asset.file_name}
                    </Typography>

                    {/* File Size */}
                    <Typography variant="caption" color="text.secondary" component="span" sx={{ flexShrink: 0 }}>
                      ({formatFileSize(asset.size)})
                    </Typography>
                  </Box>

                  {/* *** KEY CHANGE 3: Delete Button as a direct child *** */}
                  <IconButton
                    aria-label="delete"
                    onClick={() => handleDelete(asset.key)}
                    size="small"
                    color="error"
                    sx={{ ml: 2, flexShrink: 0 }}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </ListItem>
              ))
            )}
          </List>
        </Box>
      </Box>{" "}
      {/* --- 2. Upload Form (Dropzone Integration) --- */}
      <Typography variant="subtitle1" sx={{ mt: 3 }} gutterBottom>
        {t("assetManager.uploadTitle")}
      </Typography>
      <Paper
        {...getRootProps()}
        sx={{
          p: 3,
          border: "1px dashed",
          borderColor: isHighlighted ? theme.palette.primary.main : theme.palette.divider,
          borderRadius: "12px",
          cursor: "pointer",
          minHeight: "150px",
          backgroundColor: isHighlighted ? theme.palette.action.hover : theme.palette.background.paper,
          transition: "background-color 0.3s",
          display: "flex",
          flexDirection: "column",
          alignItems: filesToUpload.length ? "stretch" : "center",
          justifyContent: filesToUpload.length ? "flex-start" : "center",
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setIsHighlighted(true);
        }}
        onDragLeave={() => setIsHighlighted(false)}
      >
        <input {...getInputProps()} />
        {!filesToUpload.length ? (
          <Box textAlign="center">
            <UploadIcon sx={{ fontSize: 40, color: "text.secondary", mb: 1 }} />
            <Typography variant="body1" color="textSecondary">
              {t("documentLibrary.dropFiles")}
            </Typography>
            <Button variant="outlined" sx={{ mt: 1 }} onClick={open}>
              {t("assetManager.browseButton")}
            </Button>
          </Box>
        ) : (
          <Box sx={{ width: "100%" }}>
            <List dense>
              {filesToUpload.map((file, index) => (
                <ListItem
                  key={`${file.name}-${index}`}
                  secondaryAction={
                    <IconButton edge="end" aria-label="delete" onClick={() => handleDeleteTemp(index)}>
                      <CloseIcon fontSize="small" />
                    </IconButton>
                  }
                  sx={{ py: 0.5 }}
                >
                  <FilePresentIcon sx={{ mr: 1, color: theme.palette.text.secondary }} />
                  <ListItemText
                    primary={
                      <Typography variant="body2" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                        {file.name}
                      </Typography>
                    }
                    secondary={formatFileSize(file.size)}
                  />
                </ListItem>
              ))}
            </List>
            <Button variant="text" size="small" onClick={open} sx={{ mt: 1 }}>
              {t("assetManager.addMoreFiles")}
            </Button>
          </Box>
        )}
      </Paper>
      {/* --- 3. Action Buttons --- */}
      <Box sx={{ mt: 3, display: "flex", justifyContent: "space-between" }}>
        <Button variant="outlined" onClick={handleClose} sx={{ borderRadius: "8px" }}>
          {t("documentLibrary.cancel")}
        </Button>

        <Button
          variant="contained"
          color="primary"
          startIcon={isUploading ? <CircularProgress size={18} color="inherit" /> : <CloudUploadIcon />}
          onClick={handleUpload}
          disabled={!filesToUpload.length || isUploading}
          sx={{ borderRadius: "8px" }}
        >
          {isUploading
            ? t("assetManager.uploading") // Using 'isUploading' which combines both states
            : t("assetManager.uploadButton")}
        </Button>
      </Box>
    </Drawer>
  );
};
