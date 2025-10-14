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

import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined"; // optional visual parity
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import { Box, IconButton, Tooltip, Typography } from "@mui/material";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import { Resource } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export type ResourceRowCompactProps = {
  resource: Resource;
  onPreview?: (p: Resource) => void;
  onEdit?: (p: Resource) => void;
  onRemoveFromLibrary?: (p: Resource) => void; // caller decides library/tag context
};

export function ResourceRowCompact({
  resource: prompt,
  onPreview,
  onEdit,
  onRemoveFromLibrary,
}: ResourceRowCompactProps) {
  const { t } = useTranslation();
  const fmt = (d?: string) => (d ? dayjs(d).format("DD/MM/YYYY") : "-");
  const displayName = prompt.name || String(prompt.id);

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
      {/* Left: icon + name (parity with DocumentRowCompact) */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0, overflow: "hidden" }}>
        <InsertDriveFileOutlinedIcon fontSize="small" />
        <Typography
          variant="body2"
          noWrap
          sx={{ maxWidth: "60%", cursor: onPreview ? "pointer" : "default" }}
          onClick={() => onPreview?.(prompt)}
        >
          {displayName}
        </Typography>
      </Box>

      {/* Middle: updated date (parity with document date pill) */}
      <Tooltip title={prompt.updated_at || ""}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
          <EventAvailableIcon fontSize="inherit" />
          <Typography variant="caption" noWrap>
            {fmt(prompt.updated_at)}
          </Typography>
        </Box>
      </Tooltip>

      {/* Right: actions */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0, ml: 2 }}>
        {onPreview && (
          <Tooltip title={t("resourceLibrary.preview")}>
            <IconButton size="small" onClick={() => onPreview(prompt)} aria-label="preview">
              <VisibilityOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
        {onEdit && (
          <Tooltip title={t("resourceLibrary.edit")}>
            <IconButton size="small" onClick={() => onEdit(prompt)} aria-label="edit">
              <EditOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
        {onRemoveFromLibrary && (
          <Tooltip title={t("documentLibrary.removeFromLibrary")}>
            <IconButton size="small" onClick={() => onRemoveFromLibrary(prompt)} aria-label="remove-from-library">
              <DeleteOutlineIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
}
