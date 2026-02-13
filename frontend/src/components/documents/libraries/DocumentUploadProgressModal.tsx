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

import {
  Box,
  Button,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Paper,
  Typography,
  useTheme,
} from "@mui/material";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ProgressFileStatus, ProgressStep, ProgressStepper } from "../../ProgressStepper";

interface DocumentUploadProgressModalProps {
  open: boolean;
  onClose: (reason?: "backdropClick" | "escapeKeyDown" | "closeButton") => void;
  isLoading: boolean;
  processedCount: number;
  totalUploads: number;
  progressPercent: number;
  steps: ProgressStep[];
  fileStatuses?: Record<string, ProgressFileStatus>;
  isUploadFinished: boolean;
}

export const DocumentUploadProgressModal: React.FC<DocumentUploadProgressModalProps> = ({
  open,
  onClose,
  isLoading,
  processedCount,
  totalUploads,
  progressPercent,
  steps,
  fileStatuses,
  isUploadFinished,
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const [showDetails, setShowDetails] = useState(true);
  const detailsScrollRef = useRef<HTMLDivElement | null>(null);

  const failedDocuments = useMemo(() => {
    const latestByFile = new Map<string, ProgressStep>();
    steps.forEach((step) => {
      if (step.filename) {
        latestByFile.set(step.filename, step);
      }
    });

    const failures = Array.from(latestByFile.values()).filter((step) => step.status === "failed");
    const knownFailures = new Set(failures.map((step) => step.filename));

    if (fileStatuses) {
      Object.entries(fileStatuses).forEach(([filename, status]) => {
        if (!status?.failed || knownFailures.has(filename)) return;
        failures.push({
          filename,
          step: "processing",
          status: "failed",
          error: "Processing failed",
        });
      });
    }

    return failures;
  }, [fileStatuses, steps]);

  useEffect(() => {
    if (!showDetails || !open) return;
    if (!detailsScrollRef.current) return;
    detailsScrollRef.current.scrollTop = detailsScrollRef.current.scrollHeight;
  }, [steps, showDetails, open]);

  const handleClose = (reason?: "backdropClick" | "escapeKeyDown" | "closeButton") => {
    const isLocked = isLoading || !isUploadFinished;
    if (isLocked && (reason === "backdropClick" || reason === "escapeKeyDown")) {
      return;
    }
    onClose(reason);
  };

  return (
    <Dialog
      open={open}
      onClose={(_, reason) => handleClose(reason as "backdropClick" | "escapeKeyDown")}
      disableEscapeKeyDown={isLoading || !isUploadFinished}
      fullWidth
      maxWidth="sm"
    >
      <DialogTitle>{t("documentLibrary.bulkUploadModalTitle")}</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <Typography variant="body1" fontWeight="medium">
            {t("documentLibrary.bulkUploadProgressSummary", {
              processed: processedCount,
              total: totalUploads,
            })}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={progressPercent}
            sx={{
              borderRadius: 1,
              height: 8,
              backgroundColor: theme.palette.action.hover,
              "& .MuiLinearProgress-bar": {
                transition: "width 0.3s ease",
                backgroundColor: theme.palette.primary.main,
                animation: "none",
              },
            }}
          />
          <Button
            variant="outlined"
            size="small"
            onClick={() => setShowDetails((prev) => !prev)}
            sx={{ alignSelf: "flex-start", borderRadius: "8px" }}
          >
            {showDetails ? t("documentLibrary.bulkUploadHideDetails") : t("documentLibrary.bulkUploadShowDetails")}
          </Button>
        </Box>

        <Box sx={{ maxHeight: "50vh", overflowY: "auto", pr: 0.5 }} ref={detailsScrollRef}>
          <Collapse in={showDetails} unmountOnExit>
            <ProgressStepper steps={steps} fileStatuses={fileStatuses} />
          </Collapse>
        </Box>

        {isUploadFinished && (
          <Paper
            variant="outlined"
            sx={{
              mt: 1,
              p: 2,
              borderColor: "primary.light",
            }}
          >
            <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 1 }}>
              {t("documentLibrary.bulkUploadCompletedSummary", {
                processed: processedCount,
                total: totalUploads,
              })}
            </Typography>

            {failedDocuments.length ? (
              <>
                <Typography variant="body2" color="text.primary" sx={{ mb: 1 }}>
                  {t("documentLibrary.bulkUploadErrorsTitle")}
                </Typography>
                <Box
                  sx={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 1,
                    maxHeight: "22vh",
                    overflowY: "auto",
                    pr: 1,
                    pt: 0.5,
                    pb: 0.5,
                  }}
                >
                  {failedDocuments.map((step) => (
                    <Paper key={step.filename} variant="outlined" sx={{ p: 1.5, borderRadius: 1.5 }}>
                      <Typography variant="body2" fontWeight="medium">
                        {step.filename}
                      </Typography>
                      <Typography variant="caption" color="error">
                        {step.error || t("documentLibrary.bulkUploadUnknownError")}
                      </Typography>
                    </Paper>
                  ))}
                </Box>
              </>
            ) : (
              <Typography variant="body2" color="text.primary">
                {t("documentLibrary.bulkUploadNoErrors")}
              </Typography>
            )}
          </Paper>
        )}
      </DialogContent>
      <DialogActions>
        <Button
          onClick={() => handleClose("closeButton")}
          disabled={isLoading && !isUploadFinished}
          sx={{ borderRadius: "8px" }}
        >
          {t("common.close")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
