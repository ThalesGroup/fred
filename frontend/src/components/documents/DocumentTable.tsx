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

import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import {
  Avatar,
  Box,
  Checkbox,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Tooltip,
  Typography,
} from "@mui/material";
import dayjs from "dayjs";
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { DOCUMENT_PROCESSING_STAGES, useUpdateDocumentRetrievableMutation } from "../../slices/documentApi";
import {
  TagWithDocumentsId,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";
import { getDocumentIcon } from "./DocumentIcon";
import { CustomRowAction, DocumentTableRowActionsMenu } from "./DocumentTableRowActionsMenu";
import { CustomBulkAction, DocumentTableSelectionToolbar } from "./DocumentTableSelectionToolbar";
import { useDocumentActions } from "./useDocumentActions";

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
  librairies?: boolean;
  status?: boolean;
  retrievable?: boolean;
  actions?: boolean;
}

interface FileTableProps {
  files: FileRow[];
  onRefreshData?: () => void;
  showSelectionActions?: boolean;
  columns?: DocumentTableColumns;
  rowActions?: CustomRowAction[]; // Action in the 3 dots menu of each row. If empty list is passed, not actions.
  bulkActions?: CustomBulkAction[]; // Actions on selected documents, in the selection toolbar. If empty list is passed, no actions.
  nameClickAction?: null | ((file: FileRow) => void); // Action when clicking on file name. If undefined, open document preview. If null, no action.
  isAdmin?: boolean; // For retrievable toggle functionality
}

export const DocumentTable: React.FC<FileTableProps> = ({
  files,
  onRefreshData,
  showSelectionActions = true,
  columns = {
    fileName: true,
    dateAdded: true,
    librairies: true,
    status: true,
    retrievable: true,
    actions: true,
  },
  rowActions,
  bulkActions,
  nameClickAction,
  isAdmin = false,
}) => {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();

  // Internal state management
  const [selectedFiles, setSelectedFiles] = useState<FileRow[]>([]);
  const [sortBy, setSortBy] = useState<keyof FileRow>("date_added_to_kb");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [tagsById, setTagsById] = useState<Record<string, TagWithDocumentsId>>({});

  // API hooks
  const [updateDocumentRetrievable] = useUpdateDocumentRetrievableMutation();
  const [getTag] = useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery();

  const allSelected = selectedFiles.length === files.length && files.length > 0;

  // Fetch tag information when files change and tags column is enabled
  useEffect(() => {
    if (!columns.librairies) return;

    const allTagIds = new Set<string>();
    files.forEach((file) => {
      file.tags?.forEach((tagId) => allTagIds.add(tagId));
    });

    const fetchTags = async () => {
      const promises: Promise<void>[] = [];
      const updatedTags: Record<string, TagWithDocumentsId> = {};

      allTagIds.forEach((tagId) => {
        if (!tagsById[tagId]) {
          promises.push(
            getTag({ tagId })
              .unwrap()
              .then((tagData) => {
                updatedTags[tagId] = tagData;
              })
              .catch(() => {
                // If tag fetch fails, create a fallback tag object
                updatedTags[tagId] = {
                  id: tagId,
                  name: tagId,
                  description: null,
                  created_at: "",
                  updated_at: "",
                  owner_id: "",
                  type: "library",
                  document_ids: [],
                };
              }),
          );
        }
      });

      if (promises.length > 0) {
        await Promise.all(promises);
        setTagsById((prev) => ({ ...prev, ...updatedTags }));
      }
    };

    fetchTags();
  }, [files, columns.librairies, getTag]);

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

  // If actions are undefined, use default actions from useDocumentActions
  const { defaultBulkActions, defaultRowActions, handleDocumentPreview } = useDocumentActions();
  const rowActionsWithDefault = rowActions === undefined ? defaultRowActions : rowActions;
  const bulkActionsWithDefault = bulkActions === undefined ? defaultBulkActions : bulkActions;
  const nameClickActionWithDefault = nameClickAction === undefined ? handleDocumentPreview : nameClickAction;

  // Enhanced action handler that refreshes data after execution
  const enhancedRowActions = useMemo(
    () =>
      rowActionsWithDefault.map((action) => ({
        ...action,
        handler: async (file: FileRow) => {
          await action.handler(file);
          onRefreshData?.(); // Refresh data after action
        },
      })),
    [rowActionsWithDefault, onRefreshData],
  );

  // Enhanced bulk action handler that clears selection and refresh data after execution
  const enhancedBulkActions = useMemo(
    () =>
      bulkActionsWithDefault.map((action) => ({
        ...action,
        handler: async (files: FileRow[]) => {
          await action.handler(files);
          setSelectedFiles([]); // Clear selection after action
          onRefreshData?.(); // Refresh data after action
        },
      })),
    [bulkActionsWithDefault, setSelectedFiles, onRefreshData],
  );

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
          actions={enhancedBulkActions}
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
              {columns.librairies && <TableCell>{t("documentTable.librairies")}</TableCell>}
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
                        onClick={() => nameClickActionWithDefault?.(file)}
                        sx={{ cursor: nameClickActionWithDefault ? "pointer" : "default" }}
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
                  {columns.librairies && (
                    <TableCell>
                      <Box display="flex" flexWrap="wrap" gap={0.5}>
                        {file.tags?.map((tagId) => {
                          const tag = tagsById[tagId];
                          const tagName = tag?.name || tagId;

                          return (
                            <Tooltip key={tagId} title={tag?.description || ""}>
                              <Chip label={tagName} size="small" variant="filled" sx={{ fontSize: "0.6rem" }} />
                            </Tooltip>
                          );
                        })}
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
                      {enhancedRowActions.length > 0 && (
                        <DocumentTableRowActionsMenu file={file} actions={enhancedRowActions} />
                      )}
                    </TableCell>
                  )}
                </TableRow>
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
};
