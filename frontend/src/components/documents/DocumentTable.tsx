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
  Switch,
  Tooltip,
  Typography,
  Box,
  TableSortLabel,
  Button
} from "@mui/material";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import dayjs from "dayjs";
import { getAgentBadge } from "../../utils/avatar";
import { getDocumentIcon } from "./DocumentIcon";
import { DocumentTableRowActionsMenu } from "./DocumentTableRowActionsMenu";

export interface FileRow {
  document_uid: string;
  document_name: string;
  agent_name?: string;
  date_added_to_kb?: string;
  retrievable?: boolean;
}

interface FileTableProps {
  files: FileRow[];
  selected: string[];
  onToggleSelect: (uid: string) => void;
  onToggleAll: (checked: boolean) => void;
  onDelete: (uid: string, file_name: string) => void | Promise<void>;
  onDownload: (uid: string, file_name: string) => void | Promise<void>;
  onToggleRetrievable?: (file: FileRow) => void;
  onOpen: (uid: string, file_name: string) => void | Promise<void>;
  isAdmin?: boolean;
}

export const DocumentTable: React.FC<FileTableProps> = ({
  files,
  selected,
  onToggleSelect,
  onToggleAll,
  onDelete,
  onDownload,
  onToggleRetrievable,
  onOpen,
  isAdmin = false,
}) => {
  const allSelected = selected.length === files.length && files.length > 0;

  const [sortBy, setSortBy] = useState<keyof FileRow>("date_added_to_kb");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

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

      if (sortDirection === "asc") {
        return String(aVal).localeCompare(String(bVal));
      } else {
        return String(bVal).localeCompare(String(aVal));
      }
    });
  }, [files, sortBy, sortDirection]);

  const formatDate = (date?: string) => {
    return date ? dayjs(date).format("DD/MM/YYYY") : "-";
  };

  return (
    <>

      {selected.length > 0 && (
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          px={2}
          pt={2}
        >
          <Typography variant="subtitle2">
            {selected.length} selected
          </Typography>
          <Box display="flex" gap={1}>
            <Button
              size="small"
              variant="outlined"
              color="error"
              onClick={() => {
                selected.forEach((uid) => onDelete(uid, ""));
              }}
            >
              Delete Selected
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                selected.forEach((uid) => {
                  const link = document.createElement("a");
                  link.href = `/knowledge/v1/fullDocument/${uid}`;
                  link.download = '';
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                });
              }}
            >
              Download Selected
            </Button>
          </Box>
        </Box>
      )}

      <TableContainer component={Paper}>
        <Table size="medium">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  checked={allSelected}
                  onChange={(e) => onToggleAll(e.target.checked)}
                />
              </TableCell>
              <TableCell sx={{ width: 50 }}></TableCell> {/* Avatar column */}
              <TableCell>
                <TableSortLabel
                  active={sortBy === "agent_name"}
                  direction={sortBy === "agent_name" ? sortDirection : "asc"}
                  onClick={() => handleSortChange("agent_name")}
                >
                  Agent
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortBy === "document_name"}
                  direction={sortBy === "document_name" ? sortDirection : "asc"}
                  onClick={() => handleSortChange("document_name")}
                >
                  File Name
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortBy === "date_added_to_kb"}
                  direction={sortBy === "date_added_to_kb" ? sortDirection : "asc"}
                  onClick={() => handleSortChange("date_added_to_kb")}
                >
                  Date Added
                </TableSortLabel>
              </TableCell>
              <TableCell>Retrievable</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedFiles.map((file) => (
              <TableRow key={file.document_uid} hover>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={selected.includes(file.document_uid)}
                    onChange={() => onToggleSelect(file.document_uid)}
                  />
                </TableCell>
                <TableCell sx={{ width: 50 }}>
                  {file.agent_name ? getAgentBadge(file.agent_name) : null}
                </TableCell>
                <TableCell>
                  <Typography variant="body2" noWrap>
                    {file.agent_name || "-"}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={1}>
                    {getDocumentIcon(file.document_name)}
                    <Typography variant="body2" noWrap>
                      {file.document_name}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Tooltip title="Date added to knowledge base">
                    <Typography variant="body2">
                      <EventAvailableIcon fontSize="small" sx={{ mr: 0.5 }} />
                      {formatDate(file.date_added_to_kb)}
                    </Typography>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  {isAdmin && onToggleRetrievable ? (
                    <Switch
                      size="small"
                      checked={file.retrievable}
                      onChange={() => onToggleRetrievable(file)}
                    />
                  ) : file.retrievable ? (
                    "Yes"
                  ) : (
                    "No"
                  )}
                </TableCell>
                <TableCell align="right">
                  {isAdmin && (
                    <DocumentTableRowActionsMenu
                      onDelete={() => onDelete(file.document_uid, file.document_name)}
                      onDownload={() => onDownload(file.document_uid, file.document_name)}
                      onOpen={() => onOpen(file.document_uid, file.document_name)}
                    />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
};
