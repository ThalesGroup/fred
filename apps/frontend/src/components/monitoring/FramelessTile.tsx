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

import InfoOutlined from "@mui/icons-material/InfoOutlined";
import { Box, IconButton, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";

export function FramelessTile({
  title,
  subtitle,
  help,
  children,
}: {
  title: string;
  subtitle?: string;
  help?: string;
  children: React.ReactNode;
}) {
  const theme = useTheme();
  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        border: `1px solid ${theme.palette.divider}`,
        bgcolor: theme.palette.background.default,
        overflow: "hidden",
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="subtitle2"
            fontWeight={600}
            sx={{
              lineHeight: 1.25,
              minHeight: 20,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={title}
          >
            {title}
          </Typography>
          {subtitle && (
            <Typography
              variant="caption"
              sx={{ color: theme.palette.text.secondary, display: "block" }}
              title={subtitle}
            >
              {subtitle}
            </Typography>
          )}
        </Box>
        {help && (
          <SimpleTooltip title={help}>
            <IconButton size="small" sx={{ ml: 1 }}>
              <InfoOutlined fontSize="small" />
            </IconButton>
          </SimpleTooltip>
        )}
      </Stack>
      {children}
    </Box>
  );
}
