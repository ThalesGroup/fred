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
}

export const EmptyState = ({ icon, title, description, actionButton }: EmptyStateProps) => {
  return (
    <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" py={8} gap={1}>
      {React.cloneElement(icon as React.ReactElement, {
        sx: { fontSize: 64, color: "text.secondary", ...(icon as any)?.props?.sx },
      })}
      <Typography variant="h6" color="text.secondary">
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" textAlign="center" maxWidth={400}>
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