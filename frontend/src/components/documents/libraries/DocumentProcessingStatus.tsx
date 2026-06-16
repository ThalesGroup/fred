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

import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import { Box, Chip, CircularProgress } from "@mui/material";
import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { type DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { SimpleTooltip } from "../../../shared/ui/tooltips/Tooltips";
import { DOCUMENT_PROCESSING_STAGES } from "../../../utils/const";
import { DocumentOverallStatus, getDocumentProcessingStatus } from "../../../utils/documentProcessingStatus";

// Original per-stage pill palette (kept intentionally muted; --success was too
// saturated next to the rest of the row).
const STAGE_STYLE: Record<string, { bg: string; fg: string }> = {
  done: { bg: "#c8e6c9", fg: "#2e7d32" },
  in_progress: { bg: "#fff9c4", fg: "#f9a825" },
  failed: { bg: "#ffcdd2", fg: "#c62828" },
  not_started: { bg: "#e0e0e0", fg: "#757575" },
};

const STAGE_LABEL: Record<string, string> = { raw: "R", preview: "P", vector: "V", sql: "S", mcp: "M" };

/** The familiar R/P/V/S/M per-stage pills. Native `title` per pill so it works
 *  both inline and nested inside the chip's MUI tooltip without tooltip-in-tooltip. */
function StagePills({ doc }: { doc: DocumentMetadata }) {
  return (
    <Box sx={{ display: "flex", gap: 0.5 }}>
      {DOCUMENT_PROCESSING_STAGES.map((stage) => {
        const stageStatus = doc.processing?.stages?.[stage] ?? "not_started";
        const { bg, fg } = STAGE_STYLE[stageStatus] ?? STAGE_STYLE.not_started;
        return (
          <Box
            key={stage}
            title={`${stage}: ${stageStatus}`}
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
            {STAGE_LABEL[stage]}
          </Box>
        );
      })}
    </Box>
  );
}

/**
 * Durable processing-status indicator for a library document, derived purely from
 * the persisted `processing.stages` (so it stays correct after navigating away).
 *
 * - Pending / Processing / Failed -> a single clear status chip (detailed pills in
 *   the hover tooltip).
 * - Ready -> the familiar R/P/V/S/M pills inline, with completed stages in the
 *   theme --success green (same as the row's search icon).
 */
export function DocumentProcessingStatus({ doc }: { doc: DocumentMetadata }) {
  const { t } = useTranslation();
  const status: DocumentOverallStatus = getDocumentProcessingStatus(doc);

  // Once ready, show the detailed pills directly rather than a "Ready" chip.
  if (status === "ready") {
    return <StagePills doc={doc} />;
  }

  const config: Record<
    Exclude<DocumentOverallStatus, "ready">,
    { label: string; color: "default" | "warning" | "error"; icon: ReactNode }
  > = {
    processing: {
      label: t("documentLibrary.statusProcessing", "Processing"),
      color: "warning",
      icon: <CircularProgress size={12} thickness={6} />,
    },
    pending: {
      label: t("documentLibrary.statusPending", "Pending"),
      color: "default",
      icon: <HourglassEmptyIcon sx={{ fontSize: 14 }} />,
    },
    failed: {
      label: t("documentLibrary.statusFailed", "Failed"),
      color: "error",
      icon: <ErrorOutlineIcon sx={{ fontSize: 14 }} />,
    },
  };

  const { label, color, icon } = config[status];

  return (
    <SimpleTooltip title={<StagePills doc={doc} />}>
      <Chip
        size="small"
        color={color}
        variant="outlined"
        icon={<Box sx={{ display: "flex", alignItems: "center", ml: 0.5 }}>{icon}</Box>}
        label={label}
        sx={{ height: 22, "& .MuiChip-label": { px: 0.75, fontSize: "0.7rem" } }}
      />
    </SimpleTooltip>
  );
}
