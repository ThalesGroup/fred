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

import React from "react";
import { Typography, IconButton, List, ListItem, ListItemIcon, ListItemText } from "@mui/material";
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
          <ListItemIcon sx={{ minWidth: 32 }}>{getDocumentIcon(file.name)}</ListItemIcon>
          <ListItemText
            primary={
              <Typography variant="body2" noWrap sx={{ textAlign: "left" }}>
                {file.name}
              </Typography>
            }
          />
        </ListItem>
      ))}
    </List>
  );
};
