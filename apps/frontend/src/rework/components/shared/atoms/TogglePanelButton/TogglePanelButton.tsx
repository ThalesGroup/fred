// Copyright Thales 2026
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

import { ComponentPropsWithoutRef } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton";

// Omit the legacy HTML `color` attribute to avoid colliding with IconButton's ColorTheme prop.
interface TogglePanelButtonProps extends Omit<ComponentPropsWithoutRef<"button">, "color"> {
  open: boolean;
}

export function TogglePanelButton({ open, ...props }: TogglePanelButtonProps) {
  return (
    <IconButton
      color="on-surface"
      variant="icon"
      size="small"
      icon={{ category: "outlined", type: open ? "chevron_right" : "chevron_left" }}
      aria-label={open ? "Close options panel" : "Open options panel"}
      {...props}
    />
  );
}
