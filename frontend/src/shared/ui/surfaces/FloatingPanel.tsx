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

import { Paper, type PaperProps, useTheme } from "@mui/material";
import { getFloatingSurfaceTokens } from "./floatingSurface";

export type FloatingPanelProps = PaperProps;

export const FloatingPanel = ({ sx, elevation = 6, ...props }: FloatingPanelProps) => {
  const theme = useTheme();
  const { background, border, boxShadow } = getFloatingSurfaceTokens(theme);

  return (
    <Paper
      elevation={elevation}
      {...props}
      sx={[
        {
          bgcolor: background,
          border: `1px solid ${border}`,
          boxShadow,
          backgroundImage: "none",
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
  );
};
