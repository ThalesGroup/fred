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

import SaveIcon from "@mui/icons-material/Save";
import UploadIcon from "@mui/icons-material/Upload";
import { Box, Button, Drawer, FormControl, MenuItem, Paper, Select, Typography, useTheme } from "@mui/material";
import React, { useState } from "react";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import { streamUploadOrProcessDocument } from "../../slices/streamDocumentUpload";
import { ProgressStep, ProgressStepper } from "../ProgressStepper";
import { useToast } from "../ToastProvider";
import { DocumentDrawerTable } from "./DocumentDrawerTable";
import { DocumentLibrary } from "../../pages/DocumentLibrary";

interface DocumentUploadDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadComplete?: () => void;
  metadata?: Record<string, any>;
}

export const DocumentUploadDrawer: React.FC<DocumentUploadDrawerProps> = ({
  isOpen,
  onClose,
  onUploadComplete,
  metadata,
}) => {
  const { t } = useTranslation();
  const { showError } = useToast();
  const theme = useTheme();

  // Upload state
  const [uploadMode, setUploadMode] = useState<"upload" | "process">("process");
  const [tempFiles, setTempFiles] = useState<File[]>([]);
  const [uploadProgressSteps, setUploadProgressSteps] = useState<ProgressStep[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isHighlighted, setIsHighlighted] = useState(false);

  const { getInputProps, open } = useDropzone({
    noClick: true,
    noKeyboard: true,
    onDrop: (acceptedFiles) => {
      setTempFiles((prevFiles) => [...prevFiles, ...acceptedFiles]);
    },
  });

  const handleDeleteTemp = (index: number) => {
    const newFiles = tempFiles.filter((_, i) => i !== index);
    setTempFiles(newFiles);
  };

  const handleClose = () => {
    setTempFiles([]);
    setUploadProgressSteps([]);
    setIsLoading(false);
    onClose();
  };

  const handleAddFiles = async () => {
    setIsLoading(true);
    setUploadProgressSteps([]);

    try {
      let uploadCount = 0;
      for (const file of tempFiles) {
        try {
          console.log(`MEMREDD Uploading file: ${file.name} with metadata `, metadata);
          await streamUploadOrProcessDocument(
            file,
            uploadMode,
            (progress) => {
              setUploadProgressSteps((prev) => [
                ...prev,
                {
                  step: progress.step,
                  status: progress.status,
                  filename: file.name,
                },
              ]);
            },
            metadata,
          );
          uploadCount++;
        } catch (e) {
          console.error("Error uploading file:", e);
          showError({
            summary: "Upload Failed",
            detail: `Error uploading ${file.name}: ${e.message}`,
          });
        }
      }
    } catch (error) {
      showError({
        summary: "Upload Failed",
        detail: `Error uploading ${error}`,
      });
      console.error("Unexpected error:", error);
    } finally {
      setIsLoading(false);
      setTempFiles([]);
      setUploadProgressSteps([]);
      onUploadComplete?.();
      onClose();
    }
  };

  const handleOpenFileSelector = () => {
    setUploadProgressSteps([]);
    setTempFiles([]);
    open();
  };

  return (
    <Drawer
      anchor="right"
      open={isOpen}
      onClose={handleClose}
      PaperProps={{
        sx: {
          width: { xs: "100%", sm: 450 },
          p: 3,
          borderTopLeftRadius: 16,
          borderBottomLeftRadius: 16,
        },
      }}
    >
      <Typography variant="h5" fontWeight="bold" gutterBottom>
        {t("documentLibrary.uploadDrawerTitle")}
      </Typography>

      <FormControl fullWidth sx={{ mt: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Ingestion Mode
        </Typography>
        <Select
          value={uploadMode}
          onChange={(e) => setUploadMode(e.target.value as "upload" | "process")}
          size="small"
          sx={{ borderRadius: "8px" }}
        >
          <MenuItem value="upload">{t("documentLibrary.upload")}</MenuItem>
          <MenuItem value="process">{t("documentLibrary.uploadAndProcess")}</MenuItem>
        </Select>
      </FormControl>

      <Paper
        sx={{
          mt: 3,
          p: 3,
          border: "1px dashed",
          borderColor: "divider",
          borderRadius: "12px",
          cursor: "pointer",
          minHeight: "180px",
          maxHeight: "400px",
          overflowY: "auto",
          backgroundColor: isHighlighted ? theme.palette.action.hover : theme.palette.background.paper,
          transition: "background-color 0.3s",
          display: "block",
          textAlign: "left",
          flexDirection: "column",
          alignItems: "center",
        }}
        onClick={handleOpenFileSelector}
        onDragOver={(event) => {
          event.preventDefault();
          setIsHighlighted(true);
        }}
        onDragLeave={() => setIsHighlighted(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsHighlighted(false);
        }}
      >
        <input {...getInputProps()} />
        {!tempFiles.length ? (
          <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" height="100%">
            <UploadIcon sx={{ fontSize: 40, color: "text.secondary", mb: 2 }} />
            <Typography variant="body1" color="textSecondary">
              {t("documentLibrary.dropFiles")}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {t("documentLibrary.maxSize")}
            </Typography>
          </Box>
        ) : (
          <DocumentDrawerTable files={tempFiles} onDelete={handleDeleteTemp} />
        )}
      </Paper>

      {uploadProgressSteps.length > 0 && (
        <Box sx={{ mt: 3, width: "100%" }}>
          <ProgressStepper steps={uploadProgressSteps} />
        </Box>
      )}

      <Box sx={{ mt: 3, display: "flex", justifyContent: "space-between" }}>
        <Button variant="outlined" onClick={handleClose} sx={{ borderRadius: "8px" }}>
          {t("documentLibrary.cancel")}
        </Button>

        <Button
          variant="contained"
          color="success"
          startIcon={<SaveIcon />}
          onClick={handleAddFiles}
          disabled={!tempFiles.length || isLoading}
          sx={{ borderRadius: "8px" }}
        >
          {isLoading ? t("documentLibrary.saving") : t("documentLibrary.save")}
        </Button>
      </Box>
    </Drawer>
  );
};
