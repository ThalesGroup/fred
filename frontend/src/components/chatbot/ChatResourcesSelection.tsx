// components/chat/ChatResourceLibrariesSelection.tsx
import TextsmsIcon from "@mui/icons-material/Textsms";
import DescriptionIcon from "@mui/icons-material/Description";
import { Badge, IconButton, Popover, Tooltip } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TagType } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { ChatResourcesSelectionCard } from "./ChatResourcesSelectionCard";

export interface ChatResourcesSelectionProps {
  libraryType: TagType; // "prompt" | "template"
  selectedResourceIds: string[];
  setSelectedResourceIds: (ids: string[]) => void;
}

export function ChatResourcesSelection({
  libraryType,
  selectedResourceIds,
  setSelectedResourceIds,
}: ChatResourcesSelectionProps) {
  const { t } = useTranslation();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);
  const id = open ? "chat-resource-libs-popover" : undefined;

  const Icon = libraryType === "template" ? DescriptionIcon : TextsmsIcon;
  const tooltipText =
    libraryType === "template"
      ? t("chatbot.tooltip.selectTemplates", "Select templates")
      : t("chatbot.tooltip.selectPrompts", "Select prompts");

  return (
    <>
      <Tooltip title={tooltipText} placement="top">
        {/* badge shows count of selected resources */}
        <Badge badgeContent={selectedResourceIds.length || undefined} color="primary">
          <IconButton sx={{ fontSize: "1.6rem", padding: "8px" }} onClick={(e) => setAnchorEl(e.currentTarget)}>
            <Icon fontSize="inherit" />
          </IconButton>
        </Badge>
      </Tooltip>

      <Popover
        id={id}
        open={open}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
        transformOrigin={{ vertical: "bottom", horizontal: "center" }}
        slotProps={{ paper: { sx: { borderRadius: 4 } } }}
      >
        <ChatResourcesSelectionCard
          libraryType={libraryType}
          selectedResourceIds={selectedResourceIds}
          setSelectedResourceIds={setSelectedResourceIds}
        />
      </Popover>
    </>
  );
}
