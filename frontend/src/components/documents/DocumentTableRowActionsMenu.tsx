import MoreVertIcon from "@mui/icons-material/MoreVert";
import { IconButton, ListItemIcon, ListItemText, Menu, MenuItem } from "@mui/material";
import React, { useState } from "react";

import { useTranslation } from "react-i18next";
import { FileRow } from "./DocumentTable";

export interface CustomRowAction {
  icon: React.ReactElement;
  name: string;
  handler: (file: FileRow) => Promise<void>;
}

interface DocumentTableRowActionsMenuProps {
  file: FileRow;
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
