import React, { useState } from "react";
import { IconButton, Menu, MenuItem, ListItemIcon, ListItemText } from "@mui/material";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import VisibilityIcon from "@mui/icons-material/Visibility";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";

import { useTranslation } from "react-i18next";
import { FileRow } from "./DocumentTable";

interface DocumentTableRowActionsMenuProps {
  file: FileRow;
  onDelete: (file: FileRow) => void;
  onDownload: (file: FileRow) => void;
  onOpen: (file: FileRow) => void;
  onProcess: (file: FileRow) => void;
}

export const DocumentTableRowActionsMenu: React.FC<DocumentTableRowActionsMenuProps> = ({
  file,
  onDelete,
  onDownload,
  onOpen,
  onProcess
}) => {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);
  const { t } = useTranslation();

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
        <MenuItem
          onClick={() => {
            onOpen(file);
            setAnchorEl(null);
          }}
        >
          <ListItemIcon>
            <VisibilityIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={t("documentActions.preview")} />
        </MenuItem>
        <MenuItem
          onClick={() => {
            onDownload(file);
            setAnchorEl(null);
          }}
        >
          <ListItemIcon>
            <DownloadIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={t("documentActions.download")} />
        </MenuItem>
        <MenuItem
          onClick={() => {
            onDelete(file);
            setAnchorEl(null);
          }}
        >
          <ListItemIcon>
            <DeleteIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={t("documentActions.delete")} />
        </MenuItem>
        <MenuItem
          onClick={() => {
            onProcess(file);
            setAnchorEl(null);
          }}
        >
          <ListItemIcon>
            <RocketLaunchIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={t("documentActions.process")} />
        </MenuItem>
      </Menu>
    </>
  );
};

export default DocumentTableRowActionsMenu;
