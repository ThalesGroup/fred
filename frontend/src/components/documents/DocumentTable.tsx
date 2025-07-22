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

import React, { useMemo, useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Checkbox,
  Tooltip,
  Typography,
  Box,
  TableSortLabel,
  Chip,
  Avatar,
} from "@mui/material";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import dayjs from "dayjs";
import { getDocumentIcon } from "./DocumentIcon";
import { DocumentTableRowActionsMenu } from "./DocumentTableRowActionsMenu";
import { DocumentTableSelectionToolbar } from "./DocumentTableSelectionToolbar";
import {
  DOCUMENT_PROCESSING_STAGES,
  useDeleteDocumentMutation,
  useLazyGetDocumentRawContentQuery,
  useUpdateDocumentRetrievableMutation,
  useProcessDocumentsMutation,
  ProcessDocumentsRequest,
} from "../../slices/documentApi";
import { useTranslation } from "react-i18next";
import { useToast } from "../ToastProvider";
import { useDocumentViewer } from "./useDocumentViewer";
import { downloadFile } from "../../utils/downloadUtils";
// import CheckCircleIcon from "@mui/icons-material/CheckCircle";
// import HourglassTopIcon from "@mui/icons-material/HourglassTop";
// import CancelIcon from "@mui/icons-material/Cancel";
// import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
// import { shallowEqual } from "react-redux";
export interface FileRow {
  document_uid: string;
  document_name: string;
  date_added_to_kb?: string;
  retrievable?: boolean;
  ingestion_type?: string;
  source_type?: string;
  processing_stages?: Record<string, string>;
  tags?: string[];
}

export interface Metadata {
  metadata: any;
}

interface DocumentTableColumns {
  fileName?: boolean;
  dateAdded?: boolean;
  tags?: boolean;
  status?: boolean;
  retrievable?: boolean;
  actions?: boolean;
}

interface FileTableProps {
  files: FileRow[];
  isAdmin?: boolean;
  onRefreshData?: () => void;
  showSelectionActions?: boolean;
  columns?: DocumentTableColumns;
}

export const DocumentTable: React.FC<FileTableProps> = ({
  files,
  isAdmin = false,
  onRefreshData,
  showSelectionActions = true,
  columns = {
    fileName: true,
    dateAdded: true,
    tags: true,
    status: true,
    retrievable: true,
    actions: true,
  },
}) => {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();
  const { openDocument, DocumentViewerComponent } = useDocumentViewer();

  // Internal state management
  const [selectedFiles, setSelectedFiles] = useState<FileRow[]>([]);
  const [sortBy, setSortBy] = useState<keyof FileRow>("date_added_to_kb");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  // API hooks
  const [deleteDocument] = useDeleteDocumentMutation();
  const [triggerDownload] = useLazyGetDocumentRawContentQuery();
  const [updateDocumentRetrievable] = useUpdateDocumentRetrievableMutation();
  const [processDocuments] = useProcessDocumentsMutation();

  const allSelected = selectedFiles.length === files.length && files.length > 0;

  // Internal handlers
  const handleToggleSelect = (file: FileRow) => {
    setSelectedFiles((prev) =>
      prev.some((f) => f.document_uid === file.document_uid)
        ? prev.filter((f) => f.document_uid !== file.document_uid)
        : [...prev, file],
    );
  };

  const handleToggleAll = (checked: boolean) => {
    setSelectedFiles(checked ? [...files] : []);
  };

  const handleDelete = async (file: FileRow, showToast: boolean = true) => {
    try {
      await deleteDocument(file.document_uid).unwrap();
      if (showToast) {
        showInfo({
          summary: "Delete Success",
          detail: `${file.document_name} deleted`,
          duration: 3000,
        });
      }
      setSelectedFiles((prev) => prev.filter((f) => f.document_uid !== file.document_uid));
      if (showToast) {
        onRefreshData?.();
      }
    } catch (error) {
      if (showToast) {
        showError({
          summary: "Delete Failed",
          detail: `Could not delete document: ${error?.data?.detail || error.message}`,
        });
      }
      throw error; // Re-throw for bulk handling
    }
  };

  const handleBulkDelete = async (filesToDelete: FileRow[]) => {
    let successCount = 0;
    let failedFiles: string[] = [];

    for (const file of filesToDelete) {
      try {
        await handleDelete(file, false); // Don't show individual toasts
        successCount++;
      } catch (error) {
        failedFiles.push(file.document_name);
      }
    }

    // Show summary toasts
    if (successCount > 0) {
      showInfo({
        summary: "Delete Success",
        detail: `${successCount} document${successCount > 1 ? "s" : ""} deleted`,
        duration: 3000,
      });
    }

    if (failedFiles.length > 0) {
      showError({
        summary: "Delete Failed",
        detail: `Failed to delete: ${failedFiles.join(", ")}`,
      });
    }

    // Refresh data once at the end
    onRefreshData?.();
  };

  const handleDownload = async (file: FileRow) => {
    try {
      const { data: blob } = await triggerDownload({ document_uid: file.document_uid });
      if (blob) {
        downloadFile(blob, file.document_name || "document");
      }
    } catch (err) {
      showError({
        summary: "Download failed",
        detail: `Could not download document: ${err?.data?.detail || err.message}`,
      });
    }
  };

  const handleBulkDownload = async (filesToDownload: FileRow[]) => {
    for (const file of filesToDownload) {
      await handleDownload(file);
    }
  };

  const handleDocumentPreview = async (file: FileRow) => {
    openDocument({
      document_uid: file.document_uid,
      file_name: file.document_name,
    });
  };

  const handleToggleRetrievable = async (file: FileRow) => {
    try {
      await updateDocumentRetrievable({
        document_uid: file.document_uid,
        retrievable: !file.retrievable,
      }).unwrap();

      showInfo({
        summary: "Updated",
        detail: `"${file.document_name}" is now ${!file.retrievable ? "searchable" : "excluded from search"}.`,
      });

      onRefreshData?.();
    } catch (error) {
      console.error("Update failed:", error);
      showError({
        summary: "Error updating document",
        detail: error?.data?.detail || error.message,
      });
    }
  };

  const handleProcess = async (filesToProcess: FileRow[]) => {
    try {
      const payload: ProcessDocumentsRequest = {
        files: filesToProcess.map((f) => ({
          source_tag: f.source_type || "uploads",
          document_uid: f.document_uid,
          external_path: undefined,
          tags: f.tags || [],
        })),
        pipeline_name: "manual_ui_trigger",
      };

      const result = await processDocuments(payload).unwrap();
      showInfo({
        summary: "Processing started",
        detail: `Workflow ${result.workflow_id} submitted`,
      });
    } catch (error) {
      showError({
        summary: "Processing Failed",
        detail: error?.data?.detail || error.message,
      });
    }
  };

  const handleSortChange = (column: keyof FileRow) => {
    if (sortBy === column) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDirection("asc");
    }
  };

  const sortedFiles = useMemo(() => {
    const filesCopy = [...files];
    return filesCopy.sort((a, b) => {
      const aVal = a[sortBy] ?? "";
      const bVal = b[sortBy] ?? "";
      return sortDirection === "asc"
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    });
  }, [files, sortBy, sortDirection]);

  const formatDate = (date?: string) => {
    return date ? dayjs(date).format("DD/MM/YYYY") : "-";
  };

  return (
    <>
      {showSelectionActions && (
        <DocumentTableSelectionToolbar
          selectedFiles={selectedFiles}
          onDeleteSelected={handleBulkDelete}
          onDownloadSelected={handleBulkDownload}
          onProcessSelected={handleProcess}
          isVisible={selectedFiles.length > 0}
        />
      )}

      <TableContainer>
        <Table size="medium">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox checked={allSelected} onChange={(e) => handleToggleAll(e.target.checked)} />
              </TableCell>
              {columns.fileName && (
                <TableCell>
                  <TableSortLabel
                    active={sortBy === "document_name"}
                    direction={sortBy === "document_name" ? sortDirection : "asc"}
                    onClick={() => handleSortChange("document_name")}
                  >
                    {t("documentTable.fileName")}
                  </TableSortLabel>
                </TableCell>
              )}
              {columns.dateAdded && (
                <TableCell>
                  <TableSortLabel
                    active={sortBy === "date_added_to_kb"}
                    direction={sortBy === "date_added_to_kb" ? sortDirection : "asc"}
                    onClick={() => handleSortChange("date_added_to_kb")}
                  >
                    {t("documentTable.dateAdded")}
                  </TableSortLabel>
                </TableCell>
              )}
              {columns.tags && <TableCell>{t("documentTable.tags")}</TableCell>}
              {columns.status && <TableCell>{t("documentTable.status")}</TableCell>}
              {columns.retrievable && <TableCell>{t("documentTable.retrievableYes")}</TableCell>}
              {columns.actions && <TableCell align="right">{t("documentTable.actions")}</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedFiles.map((file) => (
              <React.Fragment key={file.document_uid}>
                <TableRow hover>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={selectedFiles.some((f) => f.document_uid === file.document_uid)}
                      onChange={() => handleToggleSelect(file)}
                    />
                  </TableCell>
                  {columns.fileName && (
                    <TableCell>
                      <Box
                        display="flex"
                        alignItems="center"
                        gap={1}
                        onClick={() => handleDocumentPreview(file)}
                        sx={{ cursor: "pointer" }}
                      >
                        {getDocumentIcon(file.document_name)}
                        <Typography variant="body2" noWrap>
                          {file.document_name}
                        </Typography>
                      </Box>
                    </TableCell>
                  )}
                  {columns.dateAdded && (
                    <TableCell>
                      <Tooltip title={file.date_added_to_kb}>
                        <Typography variant="body2">
                          <EventAvailableIcon fontSize="small" sx={{ mr: 0.5 }} />
                          {formatDate(file.date_added_to_kb)}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                  )}
                  {columns.tags && (
                    <TableCell>
                      <Box display="flex" flexWrap="wrap" gap={0.5}>
                        {file.tags?.map((tag) => (
                          <Tooltip key={tag} title={`Tag: ${tag}`}>
                            <Chip label={tag} size="small" variant="filled" sx={{ fontSize: "0.6rem" }} />
                          </Tooltip>
                        ))}
                      </Box>
                    </TableCell>
                  )}
                  {columns.status && (
                    <TableCell>
                      <Box display="flex" flexWrap="wrap" gap={0.5}>
                        {DOCUMENT_PROCESSING_STAGES.map((stage) => {
                          const status = file.processing_stages?.[stage] ?? "not_started";

                          const statusStyleMap: Record<string, { bgColor: string; color: string }> = {
                            done: {
                              bgColor: "#c8e6c9", // green
                              color: "#2e7d32",
                            },
                            in_progress: {
                              bgColor: "#fff9c4", // yellow
                              color: "#f9a825",
                            },
                            failed: {
                              bgColor: "#ffcdd2", // red
                              color: "#c62828",
                            },
                            not_started: {
                              bgColor: "#e0e0e0", // gray
                              color: "#757575",
                            },
                          };

                          const stageLabelMap: Record<string, string> = {
                            raw: "R",
                            preview: "P",
                            vector: "V",
                            sql: "S",
                            mcp: "M",
                          };

                          const label = stageLabelMap[stage] ?? "?";
                          const { bgColor, color } = statusStyleMap[status];

                          return (
                            <Tooltip key={stage} title={`${stage.replace(/_/g, " ")}: ${status}`} arrow>
                              <Avatar
                                sx={{
                                  bgcolor: bgColor,
                                  color,
                                  width: 24,
                                  height: 24,
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                }}
                              >
                                {label}
                              </Avatar>
                            </Tooltip>
                          );
                        })}
                      </Box>
                    </TableCell>
                  )}
                  {columns.retrievable && (
                    <TableCell>
                      {(() => {
                        const isRetrievable = file.retrievable;

                        return (
                          <Chip
                            label={isRetrievable ? t("documentTable.retrievableYes") : t("documentTable.retrievableNo")}
                            size="small"
                            variant="outlined"
                            onClick={isAdmin ? () => handleToggleRetrievable(file) : undefined}
                            sx={{
                              cursor: isAdmin ? "pointer" : "default",
                              backgroundColor: isRetrievable ? "#e6f4ea" : "#eceff1",
                              borderColor: isRetrievable ? "#2e7d32" : "#90a4ae",
                              color: isRetrievable ? "#2e7d32" : "#607d8b",
                              fontWeight: 500,
                              fontSize: "0.75rem",
                            }}
                          />
                        );
                      })()}
                    </TableCell>
                  )}
                  {columns.actions && (
                    <TableCell align="right">
                      {isAdmin && (
                        <DocumentTableRowActionsMenu
                          file={file}
                          onDelete={() => handleDelete(file)}
                          onDownload={() => handleDownload(file)}
                          onOpen={() => handleDocumentPreview(file)}
                          onProcess={() => handleProcess([file])}
                        />
                      )}
                    </TableCell>
                  )}
                </TableRow>
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <DocumentViewerComponent />
    </>
  );
};
