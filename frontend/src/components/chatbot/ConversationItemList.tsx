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

import React from "react";
import { Box, Stack, Typography } from "@mui/material";
import { SxProps, Theme } from "@mui/material/styles";

export type ConversationItemListItem = {
  key: string;
  primary: React.ReactNode;
  secondary?: React.ReactNode;
  startAdornment?: React.ReactNode;
  endAdornment?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
};

export type ConversationItemListProps = {
  title: React.ReactNode;
  count?: number;
  items: ConversationItemListItem[];
  emptyText?: React.ReactNode;
  headerActions?: React.ReactNode;
  sx?: SxProps<Theme>;
};

export function ConversationItemList({ title, count, items, emptyText, headerActions, sx }: ConversationItemListProps) {
  const effectiveCount = count ?? items.length;

  return (
    <Box sx={sx}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.75 }}>
        <Stack direction="row" alignItems="baseline" spacing={1} sx={{ minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }} noWrap>
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {effectiveCount}
          </Typography>
        </Stack>
        {headerActions}
      </Stack>

      {!items.length ? (
        <Typography variant="caption" color="text.secondary">
          {emptyText ?? "—"}
        </Typography>
      ) : (
        <Stack spacing={0.75}>
          {items.map((item) => (
            <Box
              key={item.key}
              onClick={item.disabled ? undefined : item.onClick}
              role={item.onClick ? "button" : undefined}
              tabIndex={item.onClick && !item.disabled ? 0 : undefined}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1,
                p: 1,
                borderRadius: 1,
                border: (t) => `1px solid ${t.palette.divider}`,
                backgroundColor: (t) => (item.disabled ? t.palette.action.disabledBackground : "transparent"),
                cursor: item.onClick && !item.disabled ? "pointer" : "default",
                "&:hover": item.onClick && !item.disabled ? { backgroundColor: "action.hover" } : undefined,
              }}
            >
              {item.startAdornment ? <Box sx={{ display: "flex", alignItems: "center" }}>{item.startAdornment}</Box> : null}
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" noWrap>
                  {item.primary}
                </Typography>
                {item.secondary ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block" }} noWrap>
                    {item.secondary}
                  </Typography>
                ) : null}
              </Box>
              {item.endAdornment ? <Box sx={{ display: "flex", alignItems: "center" }}>{item.endAdornment}</Box> : null}
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}

