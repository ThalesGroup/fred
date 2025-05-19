import React from "react";
import {
  Typography,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import { getDocumentIcon } from "./DocumentIcon";

interface TempFile {
  name: string;
}

interface TempFileTableProps {
  files: TempFile[];
  onDelete: (index: number) => void;
}

export const DocumentDrawerTable: React.FC<TempFileTableProps> = ({ files, onDelete }) => {

  return (
    <List dense disablePadding>
      {files.map((file, index) => (
        <ListItem
          key={index}
          sx={{ pl: 0 }} // Remove default left padding
          secondaryAction={
            <IconButton edge="end" onClick={() => onDelete(index)}>
              <DeleteIcon />
            </IconButton>
          }
        >
          <ListItemIcon sx={{ minWidth: 32 }}>
            {getDocumentIcon(file.name)}
          </ListItemIcon>
          <ListItemText primary={<Typography variant="body2" noWrap sx={{ textAlign: 'left' }}>{file.name}</Typography>} />
        </ListItem>
      ))}
    </List>
  );
};
