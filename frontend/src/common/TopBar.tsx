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

import { Box, Container, Fade, Grid2, Chip, useTheme, Tooltip } from "@mui/material";
import { ReactNode } from "react";

interface TopBarProps {
  title: string;
  description: string;
  children?: ReactNode; // e.g. right-hand content like date picker
  fadeIn?: boolean;
  leftLg?: number;
}

export const TopBar = ({ title, description, children, fadeIn = true, leftLg = 8 }: TopBarProps) => {
  const theme = useTheme();
  const leftGrid = leftLg ?? 8;
  const rightGrid = 12 - leftGrid;

  return (
    <Box
      sx={{
        position: "sticky",
        top: 0,
        zIndex: theme.zIndex.appBar,
        backgroundColor: theme.palette.background.paper,
        backgroundSize: "cover",
        backgroundPosition: "center",
        mb: 3,
        boxShadow: theme.shadows[4],
      }}
    >
      <Container maxWidth="xl">
        <Fade in={fadeIn} timeout={1000}>
          <Box sx={{ py: 3 }}>
            <Grid2 container spacing={3} alignItems="center">
              <Grid2 size={{ xs: 12, md: 8, lg: leftGrid }}>
                <Box>
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
                    <Chip label={title} color="primary" />
                  </Tooltip>
                </Box>
              </Grid2>
              <Grid2 size={{ xs: 12, md: 8, lg: rightGrid }}>{children}</Grid2>
            </Grid2>
          </Box>
        </Fade>
      </Container>
    </Box>
  );
};
