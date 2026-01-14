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

import AttachFileIcon from "@mui/icons-material/AttachFile";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import { Badge, Box, IconButton, Stack, Tooltip } from "@mui/material";
import { useTranslation } from "react-i18next";

const ATTACH_PANEL_W = { xs: 320, sm: 340 };

export interface AttachmentsButtonProps {
  attachmentsPanelOpen: boolean;
  attachmentCount: number;
  onToggle: () => void;
  showAttachmentsButton?: boolean;
  setupCount?: number;
  showSetupButton?: boolean;
  onOpenSetup?: (anchorEl: HTMLElement) => void;
  topSlot?: React.ReactNode;
  bottomSlot?: React.ReactNode;
}

export const AttachmentsButton = ({
  attachmentsPanelOpen,
  attachmentCount,
  onToggle,
  showAttachmentsButton = true,
  setupCount,
  showSetupButton,
  onOpenSetup,
  topSlot,
  bottomSlot,
}: AttachmentsButtonProps) => {
  const { t } = useTranslation();
  const baseRight = attachmentsPanelOpen
    ? {
        xs: ATTACH_PANEL_W.xs + 12,
        sm: ATTACH_PANEL_W.sm + 12,
        md: ATTACH_PANEL_W.sm + 12,
      }
    : 12;

  return (
    <Box
      sx={{
        position: "absolute",
        top: 12,
        right: baseRight,
        zIndex: 10,
        display: "flex",
      }}
    >
      <Stack direction="column" alignItems="flex-end" spacing={0.5}>
        {topSlot}
        <AttachmentsSetupButton
          showSetupButton={showSetupButton}
          setupCount={setupCount}
          onOpenSetup={onOpenSetup}
        />
        {showAttachmentsButton && (
          <Tooltip
            title={t("chatbot.attachments.drawerTitle", "Attachments")}
            placement="left"
            slotProps={{ popper: { sx: { backdropFilter: "none", WebkitBackdropFilter: "none" } } }}
          >
            <IconButton
              size="small"
              color={attachmentsPanelOpen ? "primary" : "default"}
              onClick={onToggle}
              aria-label="conversation-attachments"
            >
              <Badge
                color="primary"
                badgeContent={attachmentCount > 0 ? attachmentCount : undefined}
                overlap="circular"
                anchorOrigin={{ vertical: "top", horizontal: "right" }}
              >
                <AttachFileIcon fontSize="small" />
              </Badge>
            </IconButton>
          </Tooltip>
        )}
        {bottomSlot}
      </Stack>
    </Box>
  );
};

const AttachmentsSetupButton = ({
  showSetupButton,
  setupCount,
  onOpenSetup,
}: Pick<AttachmentsButtonProps, "showSetupButton" | "setupCount" | "onOpenSetup">) => {
  const { t } = useTranslation();
  if (!showSetupButton) return null;

  return (
    <Tooltip
      title={t("knowledge.viewSelector.libraries", "Libraries")}
      placement="left"
      slotProps={{ popper: { sx: { backdropFilter: "none", WebkitBackdropFilter: "none" } } }}
    >
      <IconButton
        size="small"
        onClick={(e) => onOpenSetup?.(e.currentTarget)}
        aria-label="conversation-libraries"
        disabled={!onOpenSetup}
      >
        <Badge
          color="primary"
          badgeContent={setupCount && setupCount > 0 ? setupCount : undefined}
          overlap="circular"
          anchorOrigin={{ vertical: "top", horizontal: "right" }}
        >
          <FolderOutlinedIcon fontSize="small" />
        </Badge>
      </IconButton>
    </Tooltip>
  );
};
