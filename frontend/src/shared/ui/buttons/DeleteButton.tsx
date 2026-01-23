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

import DeleteIcon from "@mui/icons-material/Delete";
import { Button } from "@mui/material";
import type { ButtonProps } from "@mui/material";

type DeleteButtonProps = Omit<ButtonProps, "startIcon" | "color"> & {
  color?: ButtonProps["color"];
  iconSize?: "inherit" | "small" | "medium" | "large";
};

// Use for labeled delete actions (e.g., "Clear", "Remove all").
export const DeleteButton = ({
  color = "error",
  iconSize = "small",
  children,
  ...props
}: DeleteButtonProps) => (
  <Button
    color={color}
    startIcon={<DeleteIcon fontSize={iconSize === "inherit" ? "inherit" : iconSize} />}
    {...props}
  >
    {children}
  </Button>
);
