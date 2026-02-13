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
import React, { useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import { SimpleTooltip } from "../../../shared/ui/tooltips/Tooltips";
import { UploadProcessProgressSummary, streamUploadOrProcessDocument } from "../../../slices/streamDocumentUpload";
import { ProcessDocumentsProgressResponse } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { ProgressFileStatus, ProgressStep } from "../../ProgressStepper";
import { useToast } from "../../ToastProvider";
import { DocumentDrawerTable } from "./DocumentDrawerTable";
import { DocumentUploadProgressModal } from "./DocumentUploadProgressModal";

const isSummaryDone = (summary: ProcessDocumentsProgressResponse) => {
  if (summary.total_documents <= 0) return false;
  const completed = summary.documents_fully_processed + summary.documents_failed + summary.documents_missing;
  return completed >= summary.total_documents;
};

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
  const [progressSummaryByFile, setProgressSummaryByFile] = useState<
    Record<string, ProcessDocumentsProgressResponse>
  >({});
  const [documentUidByFile, setDocumentUidByFile] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isHighlighted, setIsHighlighted] = useState(false);
  const [showProgressModal, setShowProgressModal] = useState(false);
  const [totalFilesCount, setTotalFilesCount] = useState(0);

  const stepDelayMs = 180;
  const displayIndexRef = useRef(0);
  const stepKeysRef = useRef<Set<string>>(new Set());

  const totalUploads = useMemo(() => {
    if (totalFilesCount) return totalFilesCount;
    const filenames = new Set<string>();
    tempFiles.forEach((file) => filenames.add(file.name));
    uploadProgressSteps.forEach((step) => filenames.add(step.filename));
    return filenames.size;
  }, [tempFiles, totalFilesCount, uploadProgressSteps]);

  const processedCount = useMemo(() => {
    const terminalStatuses = new Set(["finished", "failed", "ignored"]);
    const latestStatusByFile = new Map<string, string>();
    const summaryDoneFiles = new Set<string>();

    Object.entries(progressSummaryByFile).forEach(([filename, summary]) => {
      if (isSummaryDone(summary)) {
        summaryDoneFiles.add(filename);
      }
    });

    uploadProgressSteps.forEach((step) => {
      if (!step.filename) return;
      latestStatusByFile.set(step.filename, step.status);
    });

    let processed = summaryDoneFiles.size;
    latestStatusByFile.forEach((status, filename) => {
      if (summaryDoneFiles.has(filename)) return;
      if (terminalStatuses.has(status)) processed += 1;
    });
    return processed;
  }, [progressSummaryByFile, uploadProgressSteps]);

  const fileStatuses = useMemo(() => {
    const statuses: Record<string, ProgressFileStatus> = {};
    const filenames = new Set<string>();

    uploadProgressSteps.forEach((step) => {
      if (step.filename) filenames.add(step.filename);
    });
    Object.keys(progressSummaryByFile).forEach((filename) => filenames.add(filename));

    filenames.forEach((filename) => {
      const summary = progressSummaryByFile[filename];
      const documentUid = documentUidByFile[filename];
      const doc = summary?.documents?.find((item) => item.document_uid === documentUid);
      if (!doc) return;

      const isDone = doc.fully_processed;
      const isFailedNow = doc.has_failed;
      const processing = !isDone && !isFailedNow;

      statuses[filename] = {
        processing,
        failed: isFailedNow,
      };
    });

    return statuses;
  }, [documentUidByFile, progressSummaryByFile, uploadProgressSteps]);

  const progressPercent = totalUploads ? Math.round((processedCount / totalUploads) * 100) : 0;
  const hasInProgressStep = useMemo(
    () => uploadProgressSteps.some((step) => step.status === "in_progress"),
    [uploadProgressSteps],
  );
  const isUploadFinished = totalUploads > 0 && processedCount === totalUploads && !isLoading && !hasInProgressStep;

  const { getRootProps, getInputProps, open } = useDropzone({
    noKeyboard: true,
    onDrop: (acceptedFiles) => {
      setTempFiles((prevFiles) => {
        const existingFiles = new Map(prevFiles.map((f) => [`${f.name}-${f.size}-${f.lastModified}`, f]));

        const newUniqueFiles = acceptedFiles.filter((f) => !existingFiles.has(`${f.name}-${f.size}-${f.lastModified}`));

        if (newUniqueFiles.length < acceptedFiles.length) {
          showInfo({
            summary: t("documentDrawerTable.documentAlreadyAddedToast.summary"),
            detail: t("documentDrawerTable.documentAlreadyAddedToast.detail"),
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
    setProgressSummaryByFile({});
    setDocumentUidByFile({});
    setIsLoading(false);
    setShowProgressModal(false);
    setTotalFilesCount(0);
    displayIndexRef.current = 0;
    stepKeysRef.current = new Set();
  };

  const handleClose = () => {
    hardReset();
    onClose();
  };

  const handleAddFiles = async () => {
    setIsLoading(true);
    setUploadProgressSteps([]);
    setProgressSummaryByFile({});
    setDocumentUidByFile({});
    displayIndexRef.current = 0;
    stepKeysRef.current = new Set();
    const filesCount = tempFiles.length;
    setTotalFilesCount(filesCount);
    setShowProgressModal(filesCount > 0);

    try {
      for (const file of tempFiles) {
        try {
          await streamUploadOrProcessDocument(
            file,
            uploadMode,
            (progress) => {
              const stepFilename = progress.filename || file.name;
              const step: ProgressStep = {
                step: progress.step,
                status: progress.status,
                filename: stepFilename,
                error: progress.error,
              };
              if (progress.document_uid) {
                setDocumentUidByFile((prev) => ({
                  ...prev,
                  [stepFilename]: progress.document_uid as string,
                }));
              }
              const stepKey = `${stepFilename}::${step.step}`;
              const isKnownStep = stepKeysRef.current.has(stepKey);
              if (!isKnownStep) {
                stepKeysRef.current.add(stepKey);
              }
              if (isKnownStep) {
                setUploadProgressSteps((prev) => {
                  const existingIndex = prev.findIndex((s) => s.step === step.step && s.filename === step.filename);
                  if (existingIndex !== -1) {
                    const updated = [...prev];
                    updated[existingIndex] = step;
                    return updated;
                  }
                  return prev;
                });
                return;
              }

              const delay = uploadMode === "process" ? 0 : Math.min(displayIndexRef.current * stepDelayMs, 500);
              displayIndexRef.current += 1;
              window.setTimeout(() => {
                setUploadProgressSteps((prev) => {
                  const existingIndex = prev.findIndex((s) => s.step === step.step && s.filename === step.filename);
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
            (summaryUpdate: UploadProcessProgressSummary) => {
              setProgressSummaryByFile((prev) => ({
                ...prev,
                [summaryUpdate.filename]: summaryUpdate.summary,
              }));
            },
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
      slotProps={{
        paper: {
          sx: {
            width: { xs: "100%", sm: 450 },
            p: 3,
          },
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

      <SimpleTooltip title={t("documentLibrary.uploadDrawerTooltip")} placement="left">
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
      </SimpleTooltip>

      <Typography variant="caption" color="text.secondary" sx={{ mt: 1.5, display: "block" }}>
        {t("documentLibrary.supportedFormats")}
      </Typography>

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

      <DocumentUploadProgressModal
        open={showProgressModal}
        onClose={() => {
          setShowProgressModal(false);
          handleClose();
        }}
        isLoading={isLoading}
        processedCount={processedCount}
        totalUploads={totalUploads}
        progressPercent={progressPercent}
        steps={uploadProgressSteps}
        fileStatuses={fileStatuses}
        isUploadFinished={isUploadFinished}
      />
    </Drawer>
  );
};
