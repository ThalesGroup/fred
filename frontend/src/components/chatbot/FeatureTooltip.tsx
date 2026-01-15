import { Box, Divider, Tooltip, TooltipProps, Typography, useTheme } from "@mui/material";
import React from "react";

export type FeatureTooltipProps = {
  label: string;
  description: string;
  disabledReason?: string;
  placement?: TooltipProps["placement"];
  maxWidth?: number;
  children: React.ReactElement;
};

export function FeatureTooltip({
  label,
  description,
  disabledReason,
  placement = "left-start",
  maxWidth = 460,
  children,
}: FeatureTooltipProps) {
  const theme = useTheme();

  return (
    <Tooltip
      title={
        <Box sx={{ maxWidth }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.75 }}>
            {label}
          </Typography>
          <Divider sx={{ opacity: 0.5, mb: 0.75 }} />
          <Box sx={{ pl: 1.25, borderLeft: `2px solid ${theme.palette.divider}` }}>
            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-line" }}>
              {description}
            </Typography>
            {disabledReason ? (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 0.75, display: "block", lineHeight: 1.2, whiteSpace: "pre-line" }}
              >
                {disabledReason}
              </Typography>
            ) : null}
          </Box>
        </Box>
      }
      placement={placement}
      arrow
      slotProps={{ popper: { sx: { backdropFilter: "none", WebkitBackdropFilter: "none" } } }}
    >
      {children}
    </Tooltip>
  );
}
