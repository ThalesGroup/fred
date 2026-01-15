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
import { Badge, Box, IconButton, Stack } from "@mui/material";
import { useTranslation } from "react-i18next";
import { FeatureTooltip } from "./FeatureTooltip";

const ATTACH_PANEL_W = { xs: 320, sm: 340 };

export interface AttachmentsButtonProps {
  attachmentsPanelOpen: boolean;
  attachmentCount: number;
  onToggle: () => void;
  showAttachmentsButton?: boolean;
  attachmentsEnabled?: boolean;
  setupCount?: number;
  showSetupButton?: boolean;
  setupEnabled?: boolean;
  onOpenSetup?: (anchorEl: HTMLElement) => void;
  topSlot?: React.ReactNode;
  bottomSlot?: React.ReactNode;
}

export const AttachmentsButton = ({
  attachmentsPanelOpen,
  attachmentCount,
  onToggle,
  showAttachmentsButton = true,
  attachmentsEnabled = true,
  setupCount,
  showSetupButton,
  setupEnabled = true,
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
          setupEnabled={setupEnabled}
          onOpenSetup={onOpenSetup}
        />
        {showAttachmentsButton && (
          <FeatureTooltip
            label={t("chatbot.attachments.drawerTitle", "Attachments")}
            description={t(
              "chatbot.attachments.tooltip.description",
              "Files attached to this conversation.\nSaved per conversation; included in the runtime context when the selected agent supports attachments.",
            )}
            disabledReason={
              attachmentsEnabled
                ? undefined
                : t(
                    "chatbot.attachments.tooltip.disabled",
                    "This agent does not use attachments.\nYou can still view what is attached, but it won't influence answers.",
                  )
            }
          >
            <span>
              <IconButton
                size="small"
                color={attachmentsPanelOpen ? "primary" : "default"}
                onClick={onToggle}
                aria-label="conversation-attachments"
                disabled={!attachmentsEnabled}
                sx={!attachmentsEnabled ? { opacity: 0.45 } : undefined}
              >
                <Badge
                  color="primary"
                  badgeContent={attachmentCount > 0 ? attachmentCount : undefined}
                  overlap="circular"
                  anchorOrigin={{ vertical: "top", horizontal: "right" }}
                  sx={{
                    "& .MuiBadge-badge": {
                      fontSize: "0.65rem",
                      height: 16,
                      minWidth: 16,
                      px: 0.5,
                    },
                  }}
                >
                  <AttachFileIcon fontSize="small" />
                </Badge>
              </IconButton>
            </span>
          </FeatureTooltip>
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
  setupEnabled,
}: Pick<AttachmentsButtonProps, "showSetupButton" | "setupCount" | "onOpenSetup" | "setupEnabled">) => {
  const { t } = useTranslation();
  if (!showSetupButton) return null;

  return (
    <FeatureTooltip
      label={t("knowledge.viewSelector.libraries", "Libraries")}
      description={t(
        "knowledge.viewSelector.librariesTooltip",
        "Scope retrieval to selected document libraries for this conversation.\nSaved per conversation and used for RAG when the selected agent supports it.",
      )}
      disabledReason={
        setupEnabled
          ? undefined
          : t(
              "knowledge.viewSelector.librariesUnsupported",
              "This agent does not support library scoping.\nSelections are shown for clarity but won't be used.",
            )
      }
    >
      <span>
        <IconButton
          size="small"
          onClick={(e) => onOpenSetup?.(e.currentTarget)}
          aria-label="conversation-libraries"
          disabled={!setupEnabled || !onOpenSetup}
          sx={!setupEnabled ? { opacity: 0.45 } : undefined}
        >
          <Badge
            color="primary"
            badgeContent={setupCount && setupCount > 0 ? setupCount : undefined}
            overlap="circular"
            anchorOrigin={{ vertical: "top", horizontal: "right" }}
            sx={{
              "& .MuiBadge-badge": {
                fontSize: "0.65rem",
                height: 16,
                minWidth: 16,
                px: 0.5,
              },
            }}
          >
            <FolderOutlinedIcon fontSize="small" />
          </Badge>
        </IconButton>
      </span>
    </FeatureTooltip>
  );
};
