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

import RestartAltOutlinedIcon from "@mui/icons-material/RestartAltOutlined";
import { IconButton, Tooltip } from "@mui/material";
import type { IconButtonProps, TooltipProps } from "@mui/material";

type ResetButtonProps = Omit<IconButtonProps, "children"> & {
  iconSize?: "inherit" | "small" | "medium" | "large";
  tooltip?: TooltipProps["title"];
  tooltipPlacement?: TooltipProps["placement"];
};

// Use for reset actions that should display the standard reset icon.
export const ResetButton = ({
  iconSize = "small",
  tooltip,
  tooltipPlacement = "top",
  "aria-label": ariaLabel = "Reset",
  ...props
}: ResetButtonProps) => {
  const button = (
    <IconButton {...props} aria-label={ariaLabel}>
      <RestartAltOutlinedIcon fontSize={iconSize === "inherit" ? "inherit" : iconSize} />
    </IconButton>
  );

  if (!tooltip) return button;

  return (
    <Tooltip title={tooltip} placement={tooltipPlacement}>
      <span>{button}</span>
    </Tooltip>
  );
};
