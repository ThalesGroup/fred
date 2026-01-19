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

import CloseIcon from "@mui/icons-material/Close";
import {
  Badge,
  Box,
  Button,
  ClickAwayListener,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  useTheme,
} from "@mui/material";
import type { MouseEvent, ReactElement, ReactNode } from "react";

type ChatWidgetShellProps = {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  closeOnClickAway?: boolean;
  onClickAway?: () => void;
  disabled?: boolean;
  badgeCount?: number;
  icon: ReactElement;
  ariaLabel: string;
  tooltip?: string;
  actionLabel: string;
  onAction: (event?: MouseEvent<HTMLButtonElement>) => void;
  actionDisabled?: boolean;
  children: ReactNode;
};

const ChatWidgetShell = ({
  open,
  onOpen,
  onClose,
  closeOnClickAway = true,
  onClickAway,
  disabled = false,
  badgeCount,
  icon,
  ariaLabel,
  tooltip,
  actionLabel,
  onAction,
  actionDisabled,
  children,
}: ChatWidgetShellProps) => {
  const theme = useTheme();
  const isVisible = open;
  const count = badgeCount && badgeCount > 0 ? badgeCount : undefined;
  const resolvedActionDisabled = typeof actionDisabled === "boolean" ? actionDisabled : disabled;

  const trigger = (
    <IconButton
      size="small"
      onClick={onOpen}
      aria-label={ariaLabel}
      disabled={disabled}
      sx={{ color: disabled ? "text.disabled" : "inherit" }}
    >
      <Badge
        color={disabled ? "default" : "primary"}
        badgeContent={count}
        overlap="circular"
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        sx={{ "& .MuiBadge-badge": { opacity: disabled ? 0.5 : 1 } }}
      >
        {icon}
      </Badge>
    </IconButton>
  );

  const widgetBody = (
    <Paper
      elevation={2}
      sx={{
        width: "100%",
        minWidth: "100%",
        maxWidth: "100%",
        maxHeight: "70vh",
        borderRadius: 3,
        border: `1px solid ${theme.palette.divider}`,
        p: 1.5,
        bgcolor: theme.palette.background.paper,
      }}
    >
      <Stack spacing={1} sx={{ pb: 0.5 }}>
        <Box display="flex" alignItems="center" gap={1} sx={{ width: "100%" }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Button
              variant="outlined"
              size="small"
              onClick={onAction}
              disabled={resolvedActionDisabled}
              sx={{
                borderRadius: "8px",
                textTransform: "none",
                minHeight: 28,
                px: 1.5,
                justifyContent: "flex-start",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {actionLabel}
            </Button>
          </Box>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
        <Box>{children}</Box>
      </Stack>
    </Paper>
  );

  return (
    <Box sx={{ position: "relative", width: isVisible ? "100%" : "auto" }}>
      {!isVisible && (tooltip ? <Tooltip title={tooltip}>{trigger}</Tooltip> : trigger)}
      {isVisible && closeOnClickAway && (
        <ClickAwayListener onClickAway={onClickAway ?? onClose}>
          <Box sx={{ width: "100%" }}>{widgetBody}</Box>
        </ClickAwayListener>
      )}
      {isVisible && !closeOnClickAway && <Box sx={{ width: "100%" }}>{widgetBody}</Box>}
    </Box>
  );
};

export default ChatWidgetShell;
