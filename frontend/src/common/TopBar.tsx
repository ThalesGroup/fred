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

import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { Box, Grid2, IconButton, Stack, Tooltip, Typography, useTheme } from "@mui/material";
import { ReactNode } from "react";
import InvisibleLink from "../components/InvisibleLink";

interface TopBarProps {
  title: string;
  description: string;
  children?: ReactNode; // e.g. right-hand content like date picker
  backTo?: string; // Path to navigate back to
}

export const TopBar = ({ title, description, children, backTo }: TopBarProps) => {
  const theme = useTheme();

  return (
    <Stack
      direction="row"
      sx={{
        position: "sticky",
        top: 0,
        zIndex: theme.zIndex.appBar,
        backgroundColor: theme.palette.background.paper,
        backgroundSize: "cover",
        backgroundPosition: "center",
        mb: 3,
        boxShadow: theme.shadows[4],
        justifyContent: "space-between",
        alignItems: "center",
        px: 4,
        py: 2,
      }}
    >
      {/* Left content */}
      <Box display="flex" alignItems="center" gap={1}>
        {/* Optional back button */}
        {backTo && (
          <InvisibleLink to={backTo}>
            <IconButton size="small">
              <ArrowBackIcon />
            </IconButton>
          </InvisibleLink>
        )}

        {/* Title */}
        <Tooltip
          slotProps={{
            tooltip: {
              sx: {
                fontSize: "0.875rem", // Smaller font size (≈ 14px)
              },
            },
          }}
          title={description}
          placement="bottom-end"
          arrow
        >
          <Typography variant="h6" component="h1">
            {title}
          </Typography>
        </Tooltip>
      </Box>

      {/* Optional right part */}
      <Grid2>{children}</Grid2>
    </Stack>
  );
};
