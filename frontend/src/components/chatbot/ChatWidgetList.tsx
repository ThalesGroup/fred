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

import { List, ListItem, ListItemText, Typography } from "@mui/material";
import type { ReactNode } from "react";

export type ChatWidgetListItem = {
  id: string;
  label: string;
  secondaryAction?: ReactNode;
};

type ChatWidgetListProps = {
  items: ChatWidgetListItem[];
  emptyText: string;
};

const ChatWidgetList = ({ items, emptyText }: ChatWidgetListProps) => {
  if (!items.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ pb: 0.5 }}>
        {emptyText}
      </Typography>
    );
  }

  return (
    <List
      dense
      disablePadding
      sx={{
        maxHeight: "40vh",
        overflowY: "auto",
        "&::-webkit-scrollbar": { width: 6 },
        "&::-webkit-scrollbar-thumb": {
          backgroundColor: (theme) => theme.palette.divider,
          borderRadius: 4,
        },
      }}
    >
      {items.map((item) => (
        <ListItem
          key={item.id}
          disableGutters
          secondaryAction={item.secondaryAction}
          sx={{
            pr: item.secondaryAction ? 8.5 : 2,
            minWidth: 0,
            "& .MuiListItemSecondaryAction-root": {
              opacity: 0,
              pointerEvents: "none",
              transition: "opacity 160ms ease",
            },
            "&:hover .MuiListItemSecondaryAction-root": {
              opacity: 1,
              pointerEvents: "auto",
            },
            "&:focus-within .MuiListItemSecondaryAction-root": {
              opacity: 1,
              pointerEvents: "auto",
            },
          }}
        >
          <ListItemText
            primary={item.label}
            primaryTypographyProps={{ variant: "body2", noWrap: true, title: item.label }}
            sx={{ minWidth: 0 }}
          />
        </ListItem>
      ))}
    </List>
  );
};

export default ChatWidgetList;
