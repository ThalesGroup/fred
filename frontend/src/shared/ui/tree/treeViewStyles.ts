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

import { alpha, type Theme } from "@mui/material/styles";
import type { SxProps } from "@mui/material/styles";

export const treeConnectorStyles = (theme: Theme): SxProps<Theme> => ({
  "--tree-connector-color": alpha(theme.palette.divider, 0.7),
  "& .MuiTreeItem-group": {
    marginLeft: theme.spacing(1.5),
    paddingLeft: theme.spacing(1.5),
    borderLeft: "1px solid var(--tree-connector-color)",
  },
  "& .MuiTreeItem-content": {
    position: "relative",
    paddingLeft: theme.spacing(0.5),
  },
  "& .MuiTreeItem-content::before": {
    content: '""',
    position: "absolute",
    left: -12,
    top: "50%",
    width: 12,
    borderBottom: "1px solid var(--tree-connector-color)",
  },
  "& .MuiTreeItem-root[aria-level='1'] .MuiTreeItem-content::before": {
    display: "none",
  },
});
