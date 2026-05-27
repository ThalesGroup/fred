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

import { Paper, Typography, Box } from "@mui/material";
import { ReactNode } from "react";

interface DashboardCardProps {
  title?: string;
  children: ReactNode;
  padding?: number;
}

export default function DashboardCard({ title, children, padding = 2 }: DashboardCardProps) {
  return (
    <Paper elevation={3} sx={{ p: padding, borderRadius: 2 }}>
      {title && (
        <Box mb={2}>
          <Typography variant="subtitle1" fontWeight={600}>
            {title}
          </Typography>
        </Box>
      )}
      {children}
    </Paper>
  );
}
