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
import type { BadgeProps, TooltipProps } from "@mui/material";
import { Badge, Box, Button, ClickAwayListener, IconButton, Paper, Stack, useTheme } from "@mui/material";
import type { MouseEvent, ReactElement, ReactNode } from "react";
import { DetailedTooltip, SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";

type ChatWidgetShellProps = {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  closeOnClickAway?: boolean;
  onClickAway?: () => void;
  disabled?: boolean;
  badgeCount?: number;
  badgeColor?: BadgeProps["color"];
  badgeVariant?: BadgeProps["variant"];
  showBadgeDotWhenEmpty?: boolean;
  icon: ReactElement;
  ariaLabel: string;
  tooltip?: string;
  tooltipLabel?: string;
  tooltipDescription?: string;
  tooltipDisabledReason?: string;
  tooltipPlacement?: TooltipProps["placement"];
  actionLabel: string;
  onAction: (event?: MouseEvent<HTMLButtonElement>) => void;
  actionDisabled?: boolean;
  actionStartIcon?: ReactNode;
  headerActions?: ReactNode;
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
  badgeColor,
  badgeVariant,
  showBadgeDotWhenEmpty = false,
  icon,
  ariaLabel,
  tooltip,
  tooltipLabel,
  tooltipDescription,
  tooltipDisabledReason,
  tooltipPlacement,
  actionLabel,
  onAction,
  actionDisabled,
  actionStartIcon,
  headerActions,
  children,
}: ChatWidgetShellProps) => {
  const theme = useTheme();
  const isVisible = open;
  const hasCount = typeof badgeCount === "number" && badgeCount > 0;
  const showDot = showBadgeDotWhenEmpty && !hasCount;
  const count = hasCount ? badgeCount : undefined;
  const resolvedBadgeColor = badgeColor ?? (disabled ? "default" : "primary");
  const resolvedBadgeVariant = showDot ? "dot" : (badgeVariant ?? "standard");
  const badgeInvisible = !hasCount && !showDot;
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
        color={resolvedBadgeColor}
        badgeContent={count}
        variant={resolvedBadgeVariant}
        invisible={badgeInvisible}
        overlap="circular"
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        sx={{
          "& .MuiBadge-badge": {
            opacity: disabled ? 0.5 : 1,
            fontSize: "0.6rem",
            minWidth: 14,
            height: 14,
            padding: "0 4px",
            lineHeight: "14px",
          },
          "& .MuiBadge-dot": {
            minWidth: 8,
            height: 8,
            borderRadius: "50%",
          },
        }}
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
              startIcon={actionStartIcon}
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
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            {headerActions}
            <IconButton size="small" onClick={onClose}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>
        <Box>{children}</Box>
      </Stack>
    </Paper>
  );

  return (
    <Box sx={{ position: "relative", width: isVisible ? "100%" : "auto" }}>
      {!isVisible &&
        (tooltipLabel && tooltipDescription ? (
          <DetailedTooltip
            label={tooltipLabel}
            description={tooltipDescription}
            disabledReason={tooltipDisabledReason}
            placement={tooltipPlacement}
          >
            {trigger}
          </DetailedTooltip>
        ) : tooltip ? (
          <SimpleTooltip title={tooltip}>{trigger}</SimpleTooltip>
        ) : (
          trigger
        ))}
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
