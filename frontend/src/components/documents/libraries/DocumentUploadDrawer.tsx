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
import React, { useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import { streamUploadOrProcessDocument } from "../../../slices/streamDocumentUpload";
import { ProgressStep, ProgressStepper } from "../../ProgressStepper";
import { useToast } from "../../ToastProvider";
import { DocumentDrawerTable } from "./DocumentDrawerTable";

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
  const { showError, showInfo } = useToast();
  const theme = useTheme();

  const [uploadMode, setUploadMode] = useState<"upload" | "process">("process");
  const [tempFiles, setTempFiles] = useState<File[]>([]);
  const [uploadProgressSteps, setUploadProgressSteps] = useState<ProgressStep[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isHighlighted, setIsHighlighted] = useState(false);

  const stepDelayMs = 180;
  const closeExtraDelayMs = 500;
  const displayIndexRef = useRef(0);

  const { getRootProps, getInputProps, open } = useDropzone({
    noKeyboard: true,
    onDrop: (acceptedFiles) => {
      setTempFiles((prevFiles) => {
        const existingFiles = new Map(
          prevFiles.map((f) => [`${f.name}-${f.size}-${f.lastModified}`, f])
        );

        const newUniqueFiles = acceptedFiles.filter(
          (f) => !existingFiles.has(`${f.name}-${f.size}-${f.lastModified}`)
        );

        if (newUniqueFiles.length < acceptedFiles.length) {
          showInfo({
            summary: t("documentDrawerTable.documentAlreadyAddedToast.summary"),
            detail:  t("documentDrawerTable.documentAlreadyAddedToast.detail"),
          });
        }
        return [...prevFiles, ...newUniqueFiles];
      });
    },
  });

  const handleDeleteTemp = (index: number) => {
    setTempFiles((prevFiles) => prevFiles.filter((_, i) => i !== index));
  };

  const hardReset = () => {
    setTempFiles([]);
    setUploadProgressSteps([]);
    setIsLoading(false);
    displayIndexRef.current = 0;
  };

  const handleClose = () => {
    hardReset();
    onClose();
  };

  const handleAddFiles = async () => {
    setIsLoading(true);
    setUploadProgressSteps([]);
    displayIndexRef.current = 0;

    try {
      for (const file of tempFiles) {
        try {
          await streamUploadOrProcessDocument(
            file,
            uploadMode,
            (progress) => {
              const step: ProgressStep = {
                step: progress.step,
                status: progress.status,
                filename: file.name,
              };
              const delay = displayIndexRef.current * stepDelayMs;
              displayIndexRef.current += 1;
              window.setTimeout(() => {
                setUploadProgressSteps((prev) => {
                  const existingIndex = prev.findIndex(
                    (s) => s.step === step.step && s.filename === step.filename
                  );
                  if (existingIndex !== -1) {
                    const updated = [...prev];
                    updated[existingIndex] = step;
                    return updated;
                  }
                  return [...prev, step];
                });
              }, delay);
            },
            metadata,
          );
        } catch (e: any) {
          console.error("Error uploading file:", e);
          showError({
            summary: "Upload Failed",
            detail: `Error uploading ${file.name}: ${e.message}`,
          });
        }
      }
    } catch (error: any) {
      showError({
        summary: "Upload Failed",
        detail: `Error uploading ${error}`,
      });
      console.error("Unexpected error:", error);
    } finally {
      setIsLoading(false);
      setTempFiles([]);
      onUploadComplete?.();
      const totalDelay = displayIndexRef.current * stepDelayMs + closeExtraDelayMs;
      window.setTimeout(() => {
        handleClose();
      }, totalDelay);
    }
  };

  const handleOpenFileSelector = () => {
    open();
  };

  return (
    <Drawer
      anchor="right"
      open={isOpen}
      onClose={handleClose}
      slotProps={{ paper: {
        sx: {
          width: { xs: "100%", sm: 450 },
          p: 3,
        },
      }}}
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
        {...getRootProps()}
        sx={{
          mt: 3,
          p: 3,
          border: "1px dashed",
          borderColor: "divider",
          borderRadius: "12px",
          cursor: "pointer",
          minHeight: "220px",
          maxHeight: "60vh",
          overflowY: "auto",
          backgroundColor: isHighlighted ? theme.palette.action.hover : theme.palette.background.paper,
          transition: "background-color 0.3s",
          display: "flex",
          flexDirection: "column",
          alignItems: tempFiles.length ? "stretch" : "center",
          justifyContent: tempFiles.length ? "flex-start" : "center",
          "&::-webkit-scrollbar": {
            width: "8px",
          },
          "&::-webkit-scrollbar-thumb": {
            backgroundColor: theme.palette.divider,
            borderRadius: "4px",
          },
        }}
        onClick={handleOpenFileSelector}
        onDragOver={(event) => {
          event.preventDefault();
          setIsHighlighted(true);
        }}
        onDragLeave={() => setIsHighlighted(false)}
      >
        <input {...getInputProps()} />
        {!tempFiles.length ? (
          <Box textAlign="center">
            <UploadIcon sx={{ fontSize: 40, color: "text.secondary", mb: 2 }} />
            <Typography variant="body1" color="textSecondary">
              {t("documentLibrary.dropFiles")}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {t("documentLibrary.maxSize")}
            </Typography>
          </Box>
        ) : (
          <Box sx={{ width: "100%" }}>
            <DocumentDrawerTable
              files={tempFiles}
              onDelete={handleDeleteTemp}
              fileNameSx={{
                whiteSpace: "nowrap",
                textOverflow: "ellipsis",
                overflow: "hidden",
              }}
            />
          </Box>
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
