// components/prompts/PromptRow.tsx
import { Box, IconButton, Tooltip, Typography } from "@mui/material";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import { Resource } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export type PromptRowCompactProps = {
  resource: Resource;
  onPreview?: (p: Resource) => void;
  onEdit?: (p: Resource) => void;
  onRemoveFromLibrary?: (p: Resource) => void; // caller decides library/tag context
};

export function ResourceRowCompact({ resource: prompt, onPreview, onEdit, onRemoveFromLibrary }: PromptRowCompactProps) {
  const { t } = useTranslation();
  const fmt = (d?: string) => (d ? dayjs(d).format("DD/MM/YYYY") : "-");

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
      {/* Left: name */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0, overflow: "hidden" }}>
        <Typography
          variant="body2"
          noWrap
          sx={{ maxWidth: "60%", cursor: onPreview ? "pointer" : "default" }}
          onClick={() => onPreview?.(prompt)}
        >
          {prompt.name}
        </Typography>
      </Box>

      {/* Middle: updated date */}
      <Tooltip title={prompt.updated_at || ""}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
          <EventAvailableIcon fontSize="inherit" />
          <Typography variant="caption" noWrap>{fmt(prompt.updated_at)}</Typography>
        </Box>
      </Tooltip>

      {/* Right: actions */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0, ml: 2 }}>
        {onPreview && (
          <Tooltip title={t("resourceLibrary.preview")}>
            <IconButton size="small" onClick={() => onPreview(prompt)}>
              <VisibilityOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
        {onEdit && (
          <Tooltip title={t("resourceLibrary.edit")}>
            <IconButton size="small" onClick={() => onEdit(prompt)}>
              <EditOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
        {onRemoveFromLibrary && (
          <Tooltip title={t("documentLibrary.removeFromLibrary")}>
            <IconButton size="small" onClick={() => onRemoveFromLibrary(prompt)}>
              <DeleteOutlineIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
}
