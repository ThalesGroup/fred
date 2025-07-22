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
import { Box, Typography, Button } from "@mui/material";
import { useTranslation } from "react-i18next";
import { FileRow } from "./DocumentTable";

interface DocumentTableSelectionToolbarProps {
  selectedFiles: FileRow[];
  onDeleteSelected: (files: FileRow[]) => void;
  onDownloadSelected: (files: FileRow[]) => void;
  onProcessSelected: (files: FileRow[]) => void;
  isVisible: boolean;
}

export const DocumentTableSelectionToolbar: React.FC<DocumentTableSelectionToolbarProps> = ({
  selectedFiles,
  onDeleteSelected,
  onDownloadSelected,
  onProcessSelected,
  isVisible,
}) => {
  const { t } = useTranslation();

  if (!isVisible || selectedFiles.length === 0) {
    return null;
  }


  return (
    <Box
      sx={{
        position: "absolute",
        left: 24,
        right: 24,
        zIndex: 10,
        p: 2,
        top: 0,
        display: "flex",
        justifyContent: "flex-end",
        alignItems: "center",
      }}
    >
      <Typography pr={2} variant="subtitle2">
        {t("documentTable.selectedCount", { count: selectedFiles.length })}
      </Typography>
      <Box display="flex" gap={1}>
        <Button
          size="small"
          variant="outlined"
          color="error"
          onClick={() => onDeleteSelected(selectedFiles)}
        >
          {t("documentTable.deleteSelected")}
        </Button>
        <Button size="small" variant="outlined" onClick={() => onDownloadSelected(selectedFiles)}>
          {t("documentTable.downloadSelected")}
        </Button>
        <Button 
          size="small" 
          variant="outlined" 
          color="primary" 
          onClick={() => onProcessSelected(selectedFiles)}
        >
          {t("documentTable.processSelected")}
        </Button>
      </Box>
    </Box>
  );
};