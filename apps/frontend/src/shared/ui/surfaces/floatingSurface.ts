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

import type { Theme } from "@mui/material/styles";

export type FloatingSurfaceTokens = {
  background: string;
  border: string;
  boxShadow: string;
};

export const getFloatingSurfaceTokens = (theme: Theme): FloatingSurfaceTokens => {
  const isLight = theme.palette.mode === "light";
  return {
    background: isLight ? theme.palette.background.paper : theme.palette.grey[900],
    border: isLight ? theme.palette.divider : theme.palette.grey[800],
    boxShadow: isLight ? theme.shadows[3] : theme.shadows[6],
  };
};
