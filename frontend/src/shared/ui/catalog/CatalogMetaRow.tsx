// Copyright Thales 2025

import { Stack, Typography } from "@mui/material";
import { ReactNode } from "react";

export interface CatalogMetaRowProps {
  label: string;
  value: ReactNode;
  dense?: boolean;
}

export const CatalogMetaRow = ({ label, value, dense = false }: CatalogMetaRowProps) => {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={0.6}
      alignItems={{ xs: "flex-start", sm: "center" }}
      sx={{ minWidth: 0 }}
    >
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{
          minWidth: dense ? 72 : 92,
          lineHeight: 1.3,
          letterSpacing: 0.1,
        }}
      >
        {label}
      </Typography>
      <Typography
        variant="body2"
        color="text.primary"
        sx={{
          minWidth: 0,
          flex: 1,
          lineHeight: 1.35,
        }}
      >
        {value}
      </Typography>
    </Stack>
  );
};
