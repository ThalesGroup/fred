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

import DeleteIcon from "@mui/icons-material/Delete";
import { IconButton, List, ListItem, ListItemIcon, ListItemText, SxProps, Tooltip, Typography } from "@mui/material";
import React from "react";
import { useTranslation } from "react-i18next";
import { getDocumentIcon } from "../common/DocumentIcon";

interface TempFile {
  name: string;
}

interface TempFileTableProps {
  files: TempFile[];
  onDelete: (index: number) => void;
  fileNameSx?: SxProps;
}

export const DocumentDrawerTable: React.FC<TempFileTableProps> = ({ files, onDelete, fileNameSx }) => {
  const { t } = useTranslation();

  return (
    <List dense disablePadding>
      {files.map((file, index) => (
        <ListItem
          key={index}
          sx={{ pl: 0 }}
          secondaryAction={
            <IconButton
              edge="end"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(index);
              }}
              aria-label={t("documentDrawerTable.deleteFile")}
            >
              <DeleteIcon />
            </IconButton>
          }
        >
          <ListItemIcon sx={{ minWidth: 32 }}>{getDocumentIcon(file.name)}</ListItemIcon>
          <ListItemText
            primary={
              <Tooltip title={file.name} arrow>
                <Typography
                  variant="body2"
                  sx={{
                    textAlign: "left",
                    overflow: "hidden",
                    whiteSpace: "nowrap",
                    textOverflow: "ellipsis",
                    maxWidth: "100%",
                    cursor: "default",
                    ...fileNameSx,
                  }}
                  noWrap
                >
                  {file.name}
                </Typography>
              </Tooltip>
            }
          />
        </ListItem>
      ))}
    </List>
  );
};
