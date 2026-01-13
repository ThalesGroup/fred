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

import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import { Badge, Box, IconButton } from "@mui/material";
import { useTranslation } from "react-i18next";

const ATTACH_PANEL_W = { xs: 320, sm: 340 };

export interface AttachmentsButtonProps {
  attachmentsPanelOpen: boolean;
  attachmentCount: number;
  onToggle: () => void;
}

export const AttachmentsButton = ({ attachmentsPanelOpen, attachmentCount, onToggle }: AttachmentsButtonProps) => {
  const { t } = useTranslation();

  return (
    <Box
      sx={{
        position: "absolute",
        top: 12,
        right: attachmentsPanelOpen
          ? {
              xs: ATTACH_PANEL_W.xs + 12,
              sm: ATTACH_PANEL_W.sm + 12,
              md: ATTACH_PANEL_W.sm + 12,
            }
          : 12,
        zIndex: 10,
        display: "flex",
      }}
    >
      <IconButton
        color={attachmentsPanelOpen ? "primary" : "default"}
        onClick={onToggle}
        title={t("chatbot.attachments.drawerTitle", "Attachments")}
      >
        <Badge
          color="primary"
          badgeContent={attachmentCount > 0 ? attachmentCount : undefined}
          overlap="circular"
          anchorOrigin={{ vertical: "top", horizontal: "right" }}
        >
          <FolderOpenIcon />
        </Badge>
      </IconButton>
    </Box>
  );
};
