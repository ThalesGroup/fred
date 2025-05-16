import React, { useState } from "react";
import {
  IconButton,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText
} from "@mui/material";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import VisibilityIcon from "@mui/icons-material/Visibility"; // Import icon for viewing documents

/**
 * Props interface for the document row actions menu
 * @property onDelete - Function to handle document deletion
 * @property onDownload - Function to handle document download
 * @property onOpen - Function to handle document viewing/opening
 */
interface DocumentTableRowActionsMenuProps {
  onDelete: () => void;
  onDownload: () => void;
  onOpen: () => void; 
}

/**
 * Component that displays a menu with actions for document table rows
 * Provides options to view, download, and delete documents
 */
export const DocumentTableRowActionsMenu: React.FC<DocumentTableRowActionsMenuProps> = ({ 
  onDelete, 
  onDownload,
  onOpen
}) => {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  return (
    <>
      <IconButton
        size="small"
        onClick={(e) => setAnchorEl(e.currentTarget)}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        {/* New View/Open option */}
        <MenuItem onClick={() => { onOpen(); setAnchorEl(null); }}>
          <ListItemIcon>
            <VisibilityIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Preview" />
        </MenuItem>
        <MenuItem onClick={() => { onDownload(); setAnchorEl(null); }}>
          <ListItemIcon>
            <DownloadIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Download" />
        </MenuItem>
        <MenuItem onClick={() => { onDelete(); setAnchorEl(null); }}>
          <ListItemIcon>
            <DeleteIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Delete" />
        </MenuItem>
      </Menu>
    </>
  );
};

export default DocumentTableRowActionsMenu;