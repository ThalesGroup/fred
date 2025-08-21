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


import MoreVertIcon from "@mui/icons-material/MoreVert";
import { IconButton, ListItemIcon, ListItemText, Menu, MenuItem } from "@mui/material";
import React, { useState } from "react";

import { useTranslation } from "react-i18next";
import { DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface CustomRowAction {
  icon: React.ReactElement;
  name: string;
  handler: (file: DocumentMetadata) => Promise<void>;
}

interface DocumentTableRowActionsMenuProps {
  file: DocumentMetadata;
  actions: CustomRowAction[];
}

export const DocumentTableRowActionsMenu: React.FC<DocumentTableRowActionsMenuProps> = ({ file, actions }) => {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);
  const { t } = useTranslation();

  if (actions.length === 0) {
    return null;
  }

  return (
    <>
      <IconButton
        size="small"
        onClick={(e) => setAnchorEl(e.currentTarget)}
        aria-label={t("documentActions.menuLabel")}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        {actions.map((action, index) => (
          <MenuItem
            key={index}
            onClick={() => {
              action.handler(file);
              setAnchorEl(null);
            }}
          >
            <ListItemIcon>{React.cloneElement(action.icon, { fontSize: "small" })}</ListItemIcon>
            <ListItemText primary={action.name} />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
};

export default DocumentTableRowActionsMenu;
