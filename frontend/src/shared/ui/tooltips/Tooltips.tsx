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

import { Box, Tooltip, TooltipProps, Typography, useTheme } from "@mui/material";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { getFloatingSurfaceTokens } from "../surfaces/floatingSurface";

const TOOLTIP_ENTER_DELAY_MS = 800;
const TOOLTIP_ENTER_TOUCH_DELAY_MS = 800;

const mergeHandlers =
  <E extends React.SyntheticEvent>(theirHandler?: (event: E) => void, ourHandler?: (event: E) => void) =>
  (event: E) => {
    theirHandler?.(event);
    if (!event.defaultPrevented) ourHandler?.(event);
  };

const useDelayedTooltip = () => {
  const [open, setOpen] = useState(false);
  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (openTimerRef.current) {
      clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
  }, []);

  const scheduleOpen = useCallback(
    (delayMs: number) => {
      clearTimer();
      openTimerRef.current = setTimeout(() => {
        setOpen(true);
        openTimerRef.current = null;
      }, delayMs);
    },
    [clearTimer],
  );

  const handleOpen = useCallback(
    (delayMs: number) => {
      scheduleOpen(delayMs);
    },
    [scheduleOpen],
  );

  const handleClose = useCallback(() => {
    clearTimer();
    setOpen(false);
  }, [clearTimer]);

  useEffect(() => () => clearTimer(), [clearTimer]);

  return { open, handleOpen, handleClose };
};

const attachTooltipHandlers = (child: React.ReactElement, onOpen: (delayMs: number) => void, onClose: () => void) => {
  const childProps = child.props as React.HTMLAttributes<HTMLElement>;

  return React.cloneElement(child, {
    onMouseEnter: mergeHandlers(childProps.onMouseEnter, () => onOpen(TOOLTIP_ENTER_DELAY_MS)),
    onMouseLeave: mergeHandlers(childProps.onMouseLeave, () => onClose()),
    onFocus: mergeHandlers(childProps.onFocus, () => onOpen(TOOLTIP_ENTER_DELAY_MS)),
    onBlur: mergeHandlers(childProps.onBlur, () => onClose()),
    onTouchStart: mergeHandlers(childProps.onTouchStart, () => onOpen(TOOLTIP_ENTER_TOUCH_DELAY_MS)),
    onTouchEnd: mergeHandlers(childProps.onTouchEnd, () => onClose()),
    onTouchCancel: mergeHandlers(childProps.onTouchCancel, () => onClose()),
  });
};

export type DetailedTooltip = {
  label: string;
  description: string;
  disabledReason?: string;
  placement?: TooltipProps["placement"];
  maxWidth?: number;
  children: React.ReactElement;
};
export type SimpleTooltipProps = {
  title: React.ReactNode;
  placement?: TooltipProps["placement"];
  maxWidth?: number;
  children: React.ReactElement;
};
// A tooltip component that shows a detailed description with an optional disabled reason.
export function DetailedTooltip({
  label,
  description,
  disabledReason,
  placement = "left-start",
  maxWidth = 460,
  children,
}: DetailedTooltip) {
  const theme = useTheme();
  const { background, border, boxShadow } = getFloatingSurfaceTokens(theme);
  const { open, handleOpen, handleClose } = useDelayedTooltip();
  const trigger = attachTooltipHandlers(children, handleOpen, handleClose);

  return (
    <Tooltip
      title={
        <Box sx={{ maxWidth }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.75 }}>
            {label}
          </Typography>
          <Box sx={{ pl: 1.25, borderLeft: `2px solid ${theme.palette.divider}` }}>
            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-line" }}>
              {description}
            </Typography>
            {disabledReason ? (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 0.75, display: "block", lineHeight: 1.2, whiteSpace: "pre-line" }}
              >
                {disabledReason}
              </Typography>
            ) : null}
          </Box>
        </Box>
      }
      placement={placement}
      enterTouchDelay={TOOLTIP_ENTER_TOUCH_DELAY_MS}
      open={open}
      disableHoverListener
      disableFocusListener
      disableTouchListener
      arrow
      slotProps={{
        popper: { sx: { backdropFilter: "none", WebkitBackdropFilter: "none" } },
        tooltip: {
          sx: {
            bgcolor: background,
            color: theme.palette.text.primary,
            border: `1px solid ${border}`,
            boxShadow,
          },
        },
        arrow: { sx: { color: background } },
      }}
    >
      {trigger}
    </Tooltip>
  );
}

// A simple tooltip component that shows a title.
export function SimpleTooltip({ title, placement = "top", maxWidth = 320, children }: SimpleTooltipProps) {
  const theme = useTheme();
  const { background, border, boxShadow } = getFloatingSurfaceTokens(theme);
  const { open, handleOpen, handleClose } = useDelayedTooltip();
  const trigger = attachTooltipHandlers(children, handleOpen, handleClose);

  return (
    <Tooltip
      title={
        <Box sx={{ maxWidth }}>
          <Typography variant="body2" color="text.secondary">
            {title}
          </Typography>
        </Box>
      }
      placement={placement}
      enterTouchDelay={TOOLTIP_ENTER_TOUCH_DELAY_MS}
      open={open}
      disableHoverListener
      disableFocusListener
      disableTouchListener
      arrow
      slotProps={{
        popper: { sx: { backdropFilter: "none", WebkitBackdropFilter: "none" } },
        tooltip: {
          sx: {
            bgcolor: background,
            color: theme.palette.text.primary,
            border: `1px solid ${border}`,
            boxShadow,
          },
        },
        arrow: { sx: { color: background } },
      }}
    >
      {trigger}
    </Tooltip>
  );
}
