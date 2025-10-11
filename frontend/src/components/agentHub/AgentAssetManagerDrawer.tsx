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
import {
  Box,
  Button,
  CircularProgress,
  Drawer,
  FormControl,
  IconButton,
  // MUI Components for Listing/Form
  List,
  ListItem,
  ListItemText,
  TextField,
  Typography,
  useTheme,
} from "@mui/material";
import React, { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";

// --- RTK Query Hooks & Types ---
import {
  AgentAssetMeta,
  useDeleteAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteMutation,
  useListAssetsKnowledgeFlowV1AgentAssetsAgentGetQuery,
  useUploadAssetKnowledgeFlowV1AgentAssetsAgentUploadPostMutation,
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
  // --- State for Upload Form ---
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [assetKey, setAssetKey] = useState<string>("");
  const [contentTypeOverride, setContentTypeOverride] = useState<string>("");
  const [uploadError, setUploadError] = useState<string | null>(null);

  // --- RTK Query Initialization ---
  const {
    data: listData,
    isLoading: isListLoading,
    isFetching: isListFetching,
    refetch: refetchAssets,
  } = useListAssetsKnowledgeFlowV1AgentAssetsAgentGetQuery(
    { agent: agentId },
    { skip: !isOpen }, // Skip query if drawer is closed
  );

  const [uploadAsset, { isLoading: isUploading }] = useUploadAssetKnowledgeFlowV1AgentAssetsAgentUploadPostMutation();

  const [deleteAsset] = useDeleteAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteMutation();
  // --------------------------------

  const assets: AgentAssetMeta[] = useMemo(() => listData?.items || [], [listData]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files ? event.target.files[0] : null;
    setSelectedFile(file);
    if (file && !assetKey) {
      setAssetKey(file.name.replace(/\.[^/.]+$/, ""));
    }
    setUploadError(null);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setUploadError(t("assetManager.noFileSelected") || "Please select a file to upload.");
      return;
    }
    setUploadError(null);

    const keyToUse = assetKey || selectedFile.name.replace(/\.[^/.]+$/, "");

    // Construct FormData for multipart upload
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("key", keyToUse);
    if (contentTypeOverride) {
      formData.append("content_type_override", contentTypeOverride);
    }

    try {
      await uploadAsset({
        agent: agentId,
        // Cast is necessary as RTK-generated type expects a simplified object for FormData
        bodyUploadAssetKnowledgeFlowV1AgentAssetsAgentUploadPost: formData as any,
      }).unwrap();

      showInfo({
        summary: t("assetManager.uploadSuccessSummary") || "Asset Uploaded",
        detail:
          t("assetManager.uploadSuccessDetail", { key: keyToUse }) || `Asset '${keyToUse}' uploaded successfully.`,
      });

      // Reset form state and refetch the list
      setSelectedFile(null);
      setAssetKey("");
      setContentTypeOverride("");
      // Clear file input manually
      const fileInput = document.getElementById("asset-file-input") as HTMLInputElement;
      if (fileInput) fileInput.value = "";

      refetchAssets();
    } catch (err: any) {
      const errMsg = err?.data?.detail || err?.error || t("assetManager.unknownUploadError");
      console.error("Upload failed:", err);
      setUploadError(errMsg);
      showError({ summary: t("assetManager.uploadFailedSummary") || "Upload Failed", detail: errMsg });
    }
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
    setSelectedFile(null);
    setAssetKey("");
    setContentTypeOverride("");
    setUploadError(null);
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

      {/* --- 1. Asset Listing --- */}
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
                  secondaryAction={
                    <IconButton edge="end" aria-label="delete" onClick={() => handleDelete(asset.key)}>
                      <DeleteIcon />
                    </IconButton>
                  }
                >
                  <ListItemText
                    primary={`${asset.file_name} | ${asset.content_type} | ${formatFileSize(asset.size)}`}
                  />
                </ListItem>
              ))
            )}
          </List>
        </Box>
      </Box>

      {/* --- 2. Upload Form --- */}
      <Box
        component="form"
        sx={{ mt: 3, p: 2, border: `1px dashed ${theme.palette.primary.light}`, borderRadius: "8px" }}
      >
        <Typography variant="subtitle1" gutterBottom>
          {t("assetManager.uploadTitle")}
        </Typography>

        <FormControl fullWidth margin="normal">
          <TextField
            id="asset-file-input"
            type="file"
            onChange={handleFileChange}
            required
            size="small"
            InputLabelProps={{ shrink: true }}
            inputProps={{ accept: "*" }}
            label={t("assetManager.labelFile")}
            disabled={isUploading}
          />
        </FormControl>

        <FormControl fullWidth margin="normal">
          <TextField
            label={t("assetManager.labelKey")}
            size="small"
            value={assetKey}
            onChange={(e) => setAssetKey(e.target.value)}
            placeholder={selectedFile?.name.replace(/\.[^/.]+$/, "") || t("assetManager.keyPlaceholder")}
            required
            disabled={isUploading}
          />
        </FormControl>

        <FormControl fullWidth margin="normal">
          <TextField
            label={t("assetManager.labelContentTypeOverride")}
            size="small"
            value={contentTypeOverride}
            onChange={(e) => setContentTypeOverride(e.target.value)}
            placeholder="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            disabled={isUploading}
          />
        </FormControl>

        {uploadError &&
          showError({
            summary: t("libraryCreateDrawer.validationError"),
            detail: uploadError,
          })}
        <Button
          fullWidth
          variant="contained"
          color="primary"
          startIcon={isUploading ? <CircularProgress size={18} color="inherit" /> : <CloudUploadIcon />}
          onClick={handleUpload}
          disabled={!selectedFile || isUploading || !assetKey}
          sx={{ mt: 2, borderRadius: "8px" }}
        >
          {isUploading ? t("assetManager.uploading") : t("assetManager.uploadButton")}
        </Button>
      </Box>
    </Drawer>
  );
};
