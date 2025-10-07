// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//     http://www.apache.org/licenses/LICENSE-2.0
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import SearchIcon from "@mui/icons-material/Search";
import SearchOffIcon from "@mui/icons-material/SearchOff";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import { Box, IconButton, Tooltip, Typography } from "@mui/material";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";

import { usePermissions } from "../../../security/usePermissions";
import { type DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DOCUMENT_PROCESSING_STAGES } from "../../../utils/const";
import { getDocumentIcon } from "../common/DocumentIcon";

import KeywordsPreview from "./KeywordsPreview";
import SummaryPreview from "./SummaryPreview";

export type DocumentRowCompactProps = {
  doc: DocumentMetadata;
  onPreview?: (doc: DocumentMetadata) => void;
  onPdfPreview?: (doc: DocumentMetadata) => void;
  onDownload?: (doc: DocumentMetadata) => void;
  onRemoveFromLibrary?: (doc: DocumentMetadata) => void;
  onToggleRetrievable?: (doc: DocumentMetadata) => void;
};

export function DocumentRowCompact({
  doc,
  onPreview,
  onPdfPreview,
  onDownload,
  onRemoveFromLibrary,
  onToggleRetrievable,
}: DocumentRowCompactProps) {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canToggle = can("document", "update");
  const canDeleteDocument = can("document", "delete");

  const formatDate = (date?: string) => (date ? dayjs(date).format("DD/MM/YYYY") : "-");
  const isPdf = doc.identity.document_name.toLowerCase().endsWith('.pdf');

  return (
    <Box
      sx={{
        display: "grid",
        // Columns: Name | Summary | Keywords | Preview | Status | Date | Toggle | Actions
        gridTemplateColumns: "minmax(0, 2fr) auto auto auto auto auto auto auto",
        alignItems: "center",
        columnGap: 2,
        width: "100%",
        px: 1,
        py: 0.75,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      {/* 1) Name (icon + filename) — flexible column that absorbs overflow */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, overflow: "hidden" }}>
        {getDocumentIcon(doc.identity.document_name) || <InsertDriveFileOutlinedIcon fontSize="small" />}
        <Typography
          variant="body2"
          noWrap
          sx={{ minWidth: 0, maxWidth: "100%", cursor: onPreview ? "pointer" : "default" }}
          onClick={() => onPreview?.(doc)}
          title={doc.identity.document_name}
        >
          {doc.identity.document_name || doc.identity.document_uid}
        </Typography>
      </Box>

      {/* 2) Summary (peek + dialog). Rationale: keep doc “why” close to the name. */}
      <Box sx={{ justifySelf: "start" }}>
        <SummaryPreview summary={doc.summary} docTitle={doc.identity.title ?? doc.identity.document_name} />
      </Box>

      {/* 3) Keywords (compact trigger + grouped dialog) */}
      <Box sx={{ justifySelf: "start" }}>
        {doc.summary?.keywords && doc.summary.keywords.length > 0 ? (
          <KeywordsPreview
            keywords={doc.summary.keywords}
            docTitle={doc.identity.title ?? doc.identity.document_name}
            // onChipClick={(kw) => console.log("filter by", kw)}
          />
        ) : (
          <Typography variant="caption" sx={{ opacity: 0.4 }}>
            —
          </Typography>
        )}
      </Box>

      <Box sx={{ justifySelf: "start" }}>
        {/* 🆕 Condition to show PDF button instead of standard preview */}
        {onPdfPreview && isPdf ? (
          <Tooltip 
            title={t("documentLibrary.viewOriginalPdf", "View Original PDF")}
          >
            <IconButton 
              size="small" 
              onClick={() => onPdfPreview(doc)} 
              aria-label={t("documentLibrary.viewOriginalPdf")}
            >
              <PictureAsPdfIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        ) : onPreview ? (
          // 👈 Show standard markdown preview button for non-PDF files
          <Tooltip title={t("documentLibrary.preview")}>
            <IconButton size="small" onClick={() => onPreview(doc)} aria-label={t("documentLibrary.preview")}>
              <VisibilityOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        ) : null}
      </Box>      {/* 5) Status pills */}
      <Box sx={{ display: "flex", gap: 0.5, justifySelf: "start" }}>
        {DOCUMENT_PROCESSING_STAGES.map((stage) => {
          const status = doc.processing.stages?.[stage] ?? "not_started";
          const style: Record<string, { bg: string; fg: string }> = {
            done: { bg: "#c8e6c9", fg: "#2e7d32" },
            in_progress: { bg: "#fff9c4", fg: "#f9a825" },
            failed: { bg: "#ffcdd2", fg: "#c62828" },
            not_started: { bg: "#e0e0e0", fg: "#757575" },
          };
          const label: Record<string, string> = { raw: "R", preview: "P", vector: "V", sql: "S", mcp: "M" };
          const { bg, fg } = style[status];
          return (
            <Tooltip key={stage} title={`${stage}: ${status}`} arrow>
              <Box
                sx={{
                  bgcolor: bg,
                  color: fg,
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  fontSize: "0.6rem",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {label[stage]}
              </Box>
            </Tooltip>
          );
        })}
      </Box>

      {/* 6) Date added */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, justifySelf: "start" }}>
        <Tooltip title={doc.source.date_added_to_kb}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <EventAvailableIcon fontSize="inherit" />
            <Typography variant="caption" noWrap>
              {formatDate(doc.source.date_added_to_kb)}
            </Typography>
          </Box>
        </Tooltip>
      </Box>

      {/* 7) Searchable toggle */}
      <Box sx={{ justifySelf: "start" }}>
        <Tooltip
          title={
            doc.source.retrievable
              ? t("documentLibrary.makeExcluded", "Make excluded")
              : t("documentLibrary.makeSearchable", "Make searchable")
          }
        >
          <span>
            <IconButton
              size="small"
              disabled={!canToggle}
              onClick={() => {
                if (!canToggle) return;
                onToggleRetrievable?.(doc);
              }}
              sx={{
                width: 28,
                height: 28,
                color: canToggle ? (doc.source.retrievable ? "success.main" : "error.main") : "action.disabled",
              }}
              aria-label={
                doc.source.retrievable
                  ? t("documentLibrary.searchOn", "Search on")
                  : t("documentLibrary.searchOff", "Search off")
              }
            >
              {doc.source.retrievable ? <SearchIcon fontSize="small" /> : <SearchOffIcon fontSize="small" />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {/* 8) Actions (download/remove) */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, justifySelf: "end" }}>
        {onDownload && (
          <Tooltip title={t("documentLibrary.download")}>
            <IconButton size="small" onClick={() => onDownload(doc)}>
              <DownloadIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
        {onRemoveFromLibrary && (
          <Tooltip title={t("documentLibrary.removeFromLibrary")}>
              <IconButton
                size="small"
                disabled={!canDeleteDocument}
                onClick={() => {
                  if (!canDeleteDocument) return;
                  onRemoveFromLibrary(doc);
                }}
              >
                <DeleteIcon fontSize="inherit" />
              </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
}
