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

import { Box, Tooltip, TooltipProps, Typography, useTheme } from "@mui/material";
import React from "react";
import { getFloatingSurfaceTokens } from "../surfaces/floatingSurface";

export type DetailedTooltip = {
  label: string;
  description: string;
  disabledReason?: string;
  placement?: TooltipProps["placement"];
  maxWidth?: number;
  children: React.ReactElement;
};
// A tooltip component that shows a detailed description with an optional disabled reason.
export function DetailedTooltip({
  label,
  description,
  disabledReason,
  placement = "left-start",
  maxWidth = 460,
  children,
}: DetailedTooltip) {
  const theme = useTheme();
  const { background, border, boxShadow } = getFloatingSurfaceTokens(theme);

  return (
    <Tooltip
      title={
        <Box sx={{ maxWidth }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.75 }}>
            {label}
          </Typography>
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
      slotProps={{
        popper: { sx: { backdropFilter: "none", WebkitBackdropFilter: "none" } },
        tooltip: {
          sx: {
            bgcolor: background,
            color: theme.palette.text.primary,
            border: `1px solid ${border}`,
            boxShadow,
          },
        },
        arrow: { sx: { color: background } },
      }}
    >
      {children}
    </Tooltip>
  );
}
