// Copyright Thales 2025

import { Card, CardProps, useTheme } from "@mui/material";
import { ReactNode } from "react";

export interface CatalogCardProps extends Omit<CardProps, "children"> {
  children: ReactNode;
  selected?: boolean;
  disabledTone?: boolean;
}

export const CatalogCard = ({ children, selected = false, disabledTone = false, sx, ...props }: CatalogCardProps) => {
  const theme = useTheme();

  return (
    <Card
      variant="outlined"
      {...props}
      sx={[
        {
          height: "100%",
          borderRadius: 2,
          borderColor: selected ? "primary.main" : "divider",
          backgroundImage: "none",
          boxShadow: selected ? theme.shadows[3] : "none",
          transition: "border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease",
          opacity: disabledTone ? 0.58 : 1,
          "&:hover": {
            borderColor: selected ? "primary.main" : theme.palette.text.disabled,
            boxShadow: selected ? theme.shadows[4] : theme.shadows[1],
            transform: "translateY(-1px)",
          },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {children}
    </Card>
  );
};
