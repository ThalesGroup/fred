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

import { Box, Button, Typography } from "@mui/material";
import React from "react";
import { useTranslation } from "react-i18next";
import { DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface CustomBulkAction {
  icon: React.ReactElement;
  name: string;
  handler: (files: DocumentMetadata[]) => void;
}

export interface DocumentTableSelectionToolbarProps {
  selectedFiles: DocumentMetadata[];
  actions: CustomBulkAction[];
  isVisible: boolean;
}

export const DocumentOperationsTableSelectionToolbar: React.FC<DocumentTableSelectionToolbarProps> = ({
  selectedFiles,
  actions,
  isVisible,
}) => {
  const { t } = useTranslation();

  if (!isVisible || selectedFiles.length === 0 || actions.length === 0) {
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
        {actions.map((action, index) => (
          <Button
            key={index}
            size="small"
            variant="outlined"
            startIcon={action.icon}
            onClick={() => action.handler(selectedFiles)}
          >
            {action.name}
          </Button>
        ))}
      </Box>
    </Box>
  );
};
