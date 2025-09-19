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

import { Button } from "@mui/material";
import { ReactNode } from "react";

export type QuickRangeType =
  | "today"
  | "yesterday"
  | "thisWeek"
  | "thisMonth"
  | "thisYear"
  | "last12h"
  | "last24h"
  | "last7d"
  | "last30d";

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
