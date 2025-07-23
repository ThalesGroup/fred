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
  Paper,
  Checkbox,
  Tooltip,
  Typography,
  Box,
  TableSortLabel,
  Button,
  Collapse,
  IconButton,
  Chip,
  Avatar,
} from "@mui/material";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import dayjs from "dayjs";
import { getDocumentIcon } from "./DocumentIcon";
import { DocumentTableRowActionsMenu } from "./DocumentTableRowActionsMenu";
import { DOCUMENT_PROCESSING_STAGES, useGetDocumentMetadataMutation } from "../../slices/documentApi";
import { useTranslation } from "react-i18next";
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
  source_tag?: string;         
  pull_location?: string;    
  size?: number;              
  modified_time?: number;      
  hash?: string;              
}

export interface Metadata {
  metadata: any;
}

interface FileTableProps {
  files: FileRow[];
  selectedFiles: FileRow[];
  onToggleSelect: (file: FileRow) => void;
  onToggleAll: (checked: boolean) => void;
  onDelete: (file: FileRow) => void | Promise<void>;
  onDownload: (file: FileRow) => void | Promise<void>;
  onToggleRetrievable?: (file: FileRow) => void;
  onOpen: (file: FileRow) => void | Promise<void>;
  onProcess: (file: FileRow[]) => void | Promise<void>;
  isAdmin?: boolean;
}

export const DocumentTable: React.FC<FileTableProps> = ({
  files,
  selectedFiles,
  onToggleSelect,
  onToggleAll,
  onDelete,
  onDownload,
  onToggleRetrievable,
  onOpen,
  onProcess,
  isAdmin = false,
}) => {
  const { t } = useTranslation();
  const allSelected = selectedFiles.length === files.length && files.length > 0;
  const [sortBy, setSortBy] = useState<keyof FileRow>("date_added_to_kb");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  const [openRows, setOpenRows] = useState<Record<string, boolean>>({});
  const [metadataByUid, setMetadataByUid] = useState<Record<string, Record<string, any>>>({});
  const [loadingMetadata, setLoadingMetadata] = useState<Record<string, boolean>>({});
  const [retrieveMetadata] = useGetDocumentMetadataMutation();

  const toggleRow = async (uid: string) => {
    const isOpen = openRows[uid];
    setOpenRows((prev) => ({ ...prev, [uid]: !isOpen }));

    if (!isOpen && !metadataByUid[uid]) {
      setLoadingMetadata((prev) => ({ ...prev, [uid]: true }));
      try {
        const response = await retrieveMetadata({ document_uid: uid }).unwrap();
        setMetadataByUid((prev) => ({ ...prev, [uid]: response.metadata }));
      } catch (error) {
        console.error("Failed to fetch metadata:", error);
        setMetadataByUid((prev) => ({ ...prev, [uid]: {} }));
      } finally {
        setLoadingMetadata((prev) => ({ ...prev, [uid]: false }));
      }
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
      {selectedFiles.length > 0 && (
        <Box sx={{ position: "absolute", left: 24, right: 24, zIndex: 10, p: 2, top: 0, display: "flex", justifyContent: "flex-end", alignItems: "center" }}>
          <Typography pr={2} variant="subtitle2">
            {t("documentTable.selectedCount", { count: selectedFiles.length })}
          </Typography>
          <Box display="flex" gap={1}>
            <Button
              size="small"
              variant="outlined"
              color="error"
              onClick={() => selectedFiles.forEach((f) => onDelete(f))}
            >
              {t("documentTable.deleteSelected")}
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() =>
                selectedFiles.forEach((f) => {
                  const link = document.createElement("a");
                  link.href = `/knowledge-flow/v1/fullDocument/${f.document_uid}`;
                  link.download = "";
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                })
              }
            >
              {t("documentTable.downloadSelected")}
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="primary"
              onClick={() => onProcess(selectedFiles)}
            >
              {t("documentTable.processSelected")}
            </Button>
          </Box>
        </Box>
      )}

      <TableContainer component={Paper}>

        <Table size="medium">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox checked={allSelected} onChange={(e) => onToggleAll(e.target.checked)} />
              </TableCell>
              <TableCell />
              <TableCell>
                <TableSortLabel
                  active={sortBy === "document_name"}
                  direction={sortBy === "document_name" ? sortDirection : "asc"}
                  onClick={() => handleSortChange("document_name")}
                >
                  {t("documentTable.fileName")}
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortBy === "date_added_to_kb"}
                  direction={sortBy === "date_added_to_kb" ? sortDirection : "asc"}
                  onClick={() => handleSortChange("date_added_to_kb")}
                >
                  {t("documentTable.dateAdded")}
                </TableSortLabel>
              </TableCell>
              <TableCell>{t("documentTable.tags")}</TableCell>
              <TableCell>{t("documentTable.status")}</TableCell>
              <TableCell>{t("documentTable.retrievableYes")}</TableCell>
              <TableCell align="right">{t("documentTable.actions")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedFiles.map((file) => (
              <React.Fragment key={file.document_uid}>
                <TableRow hover>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={selectedFiles.some((f) => f.document_uid === file.document_uid)}
                      onChange={() => onToggleSelect(file)}
                    />
                  </TableCell>
                  <TableCell>
                    <IconButton size="small" onClick={() => toggleRow(file.document_uid)}>
                      {openRows[file.document_uid] ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                    </IconButton>
                  </TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center" gap={1}>
                      {getDocumentIcon(file.document_name)}
                      <Typography variant="body2" noWrap>{file.document_name}</Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Tooltip title={t("documentTable.dateAddedTooltip")}>
                      <Typography variant="body2">
                        <EventAvailableIcon fontSize="small" sx={{ mr: 0.5 }} />
                        {formatDate(file.date_added_to_kb)}
                      </Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Box display="flex" flexWrap="wrap" gap={0.5}>

                      {file.tags?.map((tag) => (
                        <Tooltip key={tag} title={`Tag: ${tag}`}>
                          <Chip
                            label={tag}
                            size="small"
                            variant="filled"
                            sx={{ fontSize: "0.6rem" }}
                          />
                        </Tooltip>
                      ))}

                    </Box>
                  </TableCell>


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



                  <TableCell>
                    {(() => {
                      const isRetrievable = file.retrievable;

                      return (
                        <Chip
                          label={isRetrievable ? t("documentTable.retrievableYes") : t("documentTable.retrievableNo")}
                          size="small"
                          variant="outlined"
                          onClick={isAdmin && onToggleRetrievable ? () => onToggleRetrievable(file) : undefined}
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
                  <TableCell align="right">
                    {isAdmin && (
                      <DocumentTableRowActionsMenu
                        file={file}
                        onDelete={() => onDelete(file)}
                        onDownload={() => onDownload(file)}
                        onOpen={() => onOpen(file)}
                        onProcess={() => onProcess([file])}
                      />
                    )}
                  </TableCell>
                </TableRow>

                <TableRow>
                  <TableCell colSpan={6} sx={{ p: 0, borderBottom: "none" }}>
                    <Collapse in={openRows[file.document_uid]} timeout="auto" unmountOnExit>
                      <Box sx={{ p: 2, bgcolor: "background.default" }}>
                        {loadingMetadata[file.document_uid] ? (
                          <Typography variant="body2" fontStyle="italic" color="text.secondary">
                            {t("documentTable.loadingMetadata")}
                          </Typography>
                        ) : metadataByUid[file.document_uid] && Object.keys(metadataByUid[file.document_uid]).length > 0 ? (
                          Object.entries(metadataByUid[file.document_uid]).map(([key, value]) => (
                            <Box key={key} sx={{ display: "flex", flexDirection: "row", mb: 0.5 }}>
                              <Typography variant="body2" fontWeight={500}>{key}:</Typography>
                              <Typography variant="body2" sx={{ ml: 1 }}>
                                {typeof value === "object" ? JSON.stringify(value, null, 2) : String(value)}
                              </Typography>
                            </Box>
                          ))
                        ) : (
                          <Typography variant="body2" fontStyle="italic" color="text.secondary">
                            {t("documentTable.noMetadata")}
                          </Typography>
                        )}
                      </Box>
                    </Collapse>
                  </TableCell>
                </TableRow>
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
