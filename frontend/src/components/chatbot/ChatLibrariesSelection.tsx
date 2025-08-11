import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import TextsmsIcon from "@mui/icons-material/Textsms";
import {
  Badge,
  IconButton,
  Popover,
  Tooltip,
} from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TagType } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { LibrariesSelectionTreeCard } from "../documents/libraries/DocumentLibrariesChatSelectionCard";

export interface ChatLibrariesSelectionProps {
  selectedLibrariesIds: string[];
  setSelectedLibrariesIds: (ids: string[]) => void;
  libraryType: TagType;
}

export function ChatLibrariesSelection({
  selectedLibrariesIds,
  setSelectedLibrariesIds,
  libraryType,
}: ChatLibrariesSelectionProps) {
  const { t } = useTranslation();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const Icon = libraryType === "prompt" ? TextsmsIcon : LibraryBooksIcon;
  const tooltipText =
    libraryType === "prompt"
      ? t("chatbot.tooltip.selectPromptLibraries")
      : t("chatbot.tooltip.selectDocumentLibraries");

  const handleClick = (event: React.MouseEvent<HTMLElement>) => setAnchorEl(event.currentTarget);
  const handleClose = () => setAnchorEl(null);
  const open = Boolean(anchorEl);
  const id = open ? "chat-libraries-popover" : undefined;

  return (
    <>
      <Tooltip title={tooltipText} placement="top">
        <Badge badgeContent={selectedLibrariesIds.length > 0 ? selectedLibrariesIds.length : undefined} color="primary">
          <IconButton sx={{ fontSize: "1.6rem", padding: "8px" }} onClick={handleClick}>
            <Icon fontSize="inherit" />
          </IconButton>
        </Badge>
      </Tooltip>

      {/* Popover card */}
      <Popover
        id={id}
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{
          vertical: "top",
          horizontal: "center",
        }}
        transformOrigin={{
          vertical: "bottom",
          horizontal: "center",
        }}
        slotProps={{
          paper: {
            sx: {
              borderRadius: 4,
            },
          },
        }}
      >
        <LibrariesSelectionTreeCard
          selectedLibrariesIds={selectedLibrariesIds}
          setSelectedLibrariesIds={setSelectedLibrariesIds}
          libraryType={libraryType}
        />
      </Popover>
    </>
  );
}