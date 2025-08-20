// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0
// SPDX-License-Identifier: Apache-2.0

import { Box, IconButton, Tooltip, Typography } from "@mui/material";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import DeleteIcon from "@mui/icons-material/Delete";
import SearchIcon from "@mui/icons-material/Search";
import SearchOffIcon from "@mui/icons-material/SearchOff";

import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";

import { getDocumentIcon } from "../common/DocumentIcon";
import { DOCUMENT_PROCESSING_STAGES, type DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { usePermissions } from "../../../security/usePermissions";

export type DocumentRowCompactProps = {
  doc: DocumentMetadata;
  onPreview?: (doc: DocumentMetadata) => void;
  onRemoveFromLibrary?: (doc: DocumentMetadata) => void;
  onToggleRetrievable?: (doc: DocumentMetadata) => void;
};

export function DocumentRowCompact({
  doc,
  onPreview,
  onRemoveFromLibrary,
  onToggleRetrievable,
}: DocumentRowCompactProps) {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canToggle = can("document:toggleRetrievable");

  const formatDate = (date?: string) => {
    return date ? dayjs(date).format("DD/MM/YYYY") : "-";
  };

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        width: "100%",
        px: 1,
        py: 0.5,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      {/* Left section: icon + name + optional tags */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          flex: 1, // Fill remaining space
          minWidth: 0, // Required for truncation
          overflow: "hidden",
        }}
      >
        {getDocumentIcon(doc.identity.document_name) || <InsertDriveFileOutlinedIcon fontSize="small" />}

        <Typography
          variant="body2"
          noWrap
          sx={{
            flexShrink: 1,
            minWidth: 0,
            maxWidth: "50%",
            cursor: onPreview ? "pointer" : "default",
          }}
          onClick={() => onPreview?.(doc)}
        >
          {doc.identity.document_name || doc.identity.document_uid}
        </Typography>
      </Box>

      {/* Middle section: status & date */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          flexShrink: 0,
        }}
      >
        {/* Status */}
        <Box sx={{ display: "flex", gap: 0.5 }}>
          {DOCUMENT_PROCESSING_STAGES.map((stage) => {
            const status = doc.processing.stages?.[stage] ?? "not_started";
            const statusStyleMap: Record<string, { bgColor: string; color: string }> = {
              done: { bgColor: "#c8e6c9", color: "#2e7d32" },
              in_progress: { bgColor: "#fff9c4", color: "#f9a825" },
              failed: { bgColor: "#ffcdd2", color: "#c62828" },
              not_started: { bgColor: "#e0e0e0", color: "#757575" },
            };
            const stageLabelMap: Record<string, string> = {
              raw: "R",
              preview: "P",
              vector: "V",
              sql: "S",
              mcp: "M",
            };
            const { bgColor, color } = statusStyleMap[status];
            return (
              <Tooltip key={stage} title={`${stage}: ${status}`} arrow>
                <Box
                  sx={{
                    bgcolor: bgColor,
                    color,
                    width: 18,
                    height: 18,
                    borderRadius: "50%",
                    fontSize: "0.6rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {stageLabelMap[stage]}
                </Box>
              </Tooltip>
            );
          })}
        </Box>

        {/* Date */}
        <Tooltip title={doc.source.date_added_to_kb}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <EventAvailableIcon fontSize="inherit" />
            <Typography variant="caption" noWrap>
              {formatDate(doc.source.date_added_to_kb)}
            </Typography>
          </Box>
        </Tooltip>
        {/* Searchable */}
        <Tooltip title={doc.source.retrievable ? "Make excluded" : "Make searchable"}>
          <span>
            {" "}
            {/* needed so Tooltip works when the button is disabled */}
            <IconButton
              size="small"
              disabled={!canToggle}
              onClick={() => {
                if (!canToggle) return; // extra safety
                onToggleRetrievable?.(doc);
              }}
              sx={{
                width: 28,
                height: 28,
                color: doc.source.retrievable ? "success.main" : "error.main",
                ...(!canToggle && { color: "action.disabled" }), // optional: match disabled look
              }}
            >
              {doc.source.retrievable ? <SearchIcon fontSize="small" /> : <SearchOffIcon fontSize="small" />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {/* Right section: actions */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0, ml: 2 }}>
        {onPreview && (
          <Tooltip title={t("documentLibrary.preview")}>
            <IconButton size="small" onClick={() => onPreview(doc)}>
              <VisibilityOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
        {onRemoveFromLibrary && (
          <Tooltip title={t("documentLibrary.removeFromLibrary")}>
            <IconButton size="small" onClick={() => onRemoveFromLibrary(doc)}>
              <DeleteIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
}
