// Copyright Thales 2025

import { Chip, ChipProps } from "@mui/material";

export interface CatalogBadgeProps extends Omit<ChipProps, "size"> {
  tone?: "neutral" | "primary" | "secondary" | "success" | "warning" | "error" | "info";
}

export const CatalogBadge = ({ tone = "neutral", sx, ...props }: CatalogBadgeProps) => {
  const color =
    tone === "neutral" ? undefined : tone;

  return (
    <Chip
      size="small"
      variant="outlined"
      color={color as ChipProps["color"]}
      {...props}
      sx={[
        {
          borderRadius: 1,
          fontWeight: 500,
          "& .MuiChip-label": {
            px: 0.9,
          },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
  );
};

