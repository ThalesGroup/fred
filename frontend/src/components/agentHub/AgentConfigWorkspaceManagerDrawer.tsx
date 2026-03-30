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
import FilePresentIcon from "@mui/icons-material/FilePresent";
import UploadIcon from "@mui/icons-material/Upload";
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Paper,
  Typography,
  useTheme,
} from "@mui/material";
import React, { useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";

import { useTranslation } from "react-i18next";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";

import {
  useDeleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDeleteMutation,
  useListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetQuery,
  useUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPostMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { agentConfigPrefix, stripAgentConfigPrefix } from "../../slices/knowledgeFlow/storagePaths";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";
import { useToast } from "../ToastProvider";

interface AgentPrivateResourcesManagerProps {
  agentId: string;
}

type ListedConfigFile = {
  key: string;
  file_name: string;
  size: number | null;
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};

export const AgentPrivateResourcesManager: React.FC<AgentPrivateResourcesManagerProps> = ({ agentId }) => {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const theme = useTheme();

  const [filesToUpload, setFilesToUpload] = useState<File[]>([]);
  const [isHighlighted, setIsHighlighted] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  const {
    data: listData,
    isLoading: isListLoading,
    isFetching: isListFetching,
    refetch: refetchAssets,
  } = useListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetQuery(
    { agentId },
    { refetchOnMountOrArgChange: true },
  );

  const [uploadAsset, { isLoading: isApiLoading }] =
    useUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPostMutation();

  const [deleteAsset] = useDeleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDeleteMutation();
  const isUploading = isApiLoading || isProcessing;

  const assets: ListedConfigFile[] = useMemo(() => {
    if (!listData || !Array.isArray(listData)) return [];
    return listData
      .map((item: any) => {
        const path: string = item.path || item.key || "";
        const prefix = agentConfigPrefix(agentId);
        const normalizedPath = path.endsWith("/") ? path : `${path}/`;

        let relativeKey = stripAgentConfigPrefix(path, agentId);
        if (relativeKey.startsWith("config/")) {
          relativeKey = relativeKey.slice("config/".length);
        }
        relativeKey = relativeKey.replace(/^\/+/, "");
        const isDirectory = (item.type || "").toLowerCase() === "directory";
        const isRootPlaceholder =
          relativeKey === "" || relativeKey === "/" || normalizedPath === prefix || path === prefix;
        if (isDirectory || isRootPlaceholder) return null;
        const name = relativeKey.split("/").filter(Boolean).pop() || relativeKey;
        return {
          key: relativeKey,
          file_name: name,
          size: item.size ?? null,
        };
      })
      .filter((x): x is ListedConfigFile => !!x);
  }, [listData, agentId]);

  const { getRootProps, getInputProps, open } = useDropzone({
    noKeyboard: true,
    onDrop: (acceptedFiles) => {
      setFilesToUpload((prevFiles) => {
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
    noClick: true,
  });

  const handleDeleteTemp = (index: number) => {
    setFilesToUpload((prevFiles) => prevFiles.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (!filesToUpload.length) return;
    setIsProcessing(true);

    const filesToProcess = [...filesToUpload];
    setFilesToUpload([]);

    for (const file of filesToProcess) {
      const keyToUse = file.name;

      const formData = new FormData();
      formData.append("file", file);
      formData.append("key", keyToUse);

      try {
        await uploadAsset({
          agentId,
          bodyUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPost: formData as any,
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
      }
    }

    setIsProcessing(false);
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
          await deleteAsset({ agentId, key }).unwrap();
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

  return (
    <Box>
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
                  sx={{
                    py: 0.5,
                    px: 2,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderBottom: `1px solid ${theme.palette.divider}`,
                  }}
                >
                  <Box sx={{ flexGrow: 1, minWidth: 0, display: "flex", alignItems: "center" }}>
                    <Typography
                      variant="body2"
                      fontWeight="medium"
                      component="span"
                      sx={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        flexShrink: 1,
                        mr: 2,
                      }}
                    >
                      {asset.file_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" component="span" sx={{ flexShrink: 0 }}>
                      ({formatFileSize(asset.size)})
                    </Typography>
                  </Box>
                  <DeleteIconButton
                    aria-label="delete"
                    onClick={() => handleDelete(asset.key)}
                    size="small"
                    sx={{ ml: 2, flexShrink: 0 }}
                  />
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
      {/* --- 3. Upload Action --- */}
      <Box sx={{ mt: 3, display: "flex", justifyContent: "flex-end" }}>
        <Button
          variant="contained"
          color="primary"
          startIcon={isUploading ? <CircularProgress size={18} color="inherit" /> : <CloudUploadIcon />}
          onClick={handleUpload}
          disabled={!filesToUpload.length || isUploading}
          sx={{ borderRadius: "8px" }}
        >
          {isUploading ? t("assetManager.uploading") : t("assetManager.uploadButton")}
        </Button>
      </Box>
    </Box>
  );
};
