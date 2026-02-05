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

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  actionButton?: {
    label: string;
    onClick: () => void;
    startIcon?: React.ReactNode;
    variant?: "contained" | "outlined" | "text";
  };
  descriptionMaxWidth?: number | string;
}

export const EmptyState = ({ icon, title, description, actionButton, descriptionMaxWidth = 400 }: EmptyStateProps) => {
  return (
    <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" py={8} gap={1}>
      {React.cloneElement(icon as React.ReactElement, {
        sx: { fontSize: 64, color: "text.secondary", ...(icon as any)?.props?.sx },
      })}
      <Typography variant="h6" color="text.secondary">
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" textAlign="center" maxWidth={descriptionMaxWidth}>
        {description}
      </Typography>
      {actionButton && (
        <Button
          variant={actionButton.variant || "outlined"}
          startIcon={actionButton.startIcon}
          onClick={actionButton.onClick}
          sx={{ mt: 1 }}
        >
          {actionButton.label}
        </Button>
      )}
    </Box>
  );
};
