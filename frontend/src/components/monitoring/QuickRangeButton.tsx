// Copyright Thales 2025
// Apache-2.0

import { Button } from "@mui/material";
import { ReactNode } from "react";

export type QuickRangeType =
  | "today" | "yesterday" | "thisWeek" | "thisMonth" | "thisYear"
  | "last12h" | "last24h" | "last7d" | "last30d";

type Props = {
  isSel: boolean;
  onClick: () => void;
  label: ReactNode;
};

export default function QuickRangeButton({ isSel, onClick, label }: Props) {
  return (
    <Button
      onClick={onClick}
      variant={isSel ? "contained" : "outlined"}
      size="small"
      sx={{ px: 1.2, py: 0.3, mr: 0.5, mb: 0.5, textTransform: "none", fontSize: 12, lineHeight: 1.2 }}
    >
      {label}
    </Button>
  );
}
