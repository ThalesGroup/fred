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

import { Badge, IconButton, useTheme } from "@mui/material";
import type { BadgeProps, IconButtonProps } from "@mui/material";
import type { ReactElement } from "react";

type ToggleIconButtonProps = Omit<IconButtonProps, "children"> & {
  icon: ReactElement;
  active?: boolean;
  indicatorColor?: BadgeProps["color"];
};

// Icon-only button with a small dot indicator for the active state.
export const ToggleIconButton = ({
  icon,
  active = false,
  indicatorColor = "primary",
  ...props
}: ToggleIconButtonProps) => {
  const theme = useTheme();

  return (
    <IconButton {...props}>
      <Badge
        variant="dot"
        color={indicatorColor}
        overlap="circular"
        invisible={!active}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        sx={{ "& .MuiBadge-badge": { boxShadow: `0 0 0 1px ${theme.palette.background.paper}` } }}
      >
        {icon}
      </Badge>
    </IconButton>
  );
};
