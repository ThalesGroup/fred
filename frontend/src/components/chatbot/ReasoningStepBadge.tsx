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

import LaunchRoundedIcon from "@mui/icons-material/LaunchRounded";
import TerminalIcon from "@mui/icons-material/Terminal";
import { Box, Chip, Collapse, IconButton, ListItemButton, Stack, Tooltip, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import React, { useState } from "react";
import type { Channel, ChatMessage } from "../../slices/agentic/agenticOpenApi";

const channelColor = (c: Channel): "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning" => {
  switch (c) {
    case "plan":
      return "info";
    case "thought":
      return "secondary";
    case "observation":
      return "primary";
    case "tool_call":
      return "warning";
    case "tool_result":
      return "success";
    case "system_note":
      return "default";
    case "error":
      return "error";
    default:
      return "default";
  }
};

export default function ReasoningStepBadge({
  message: m,
  indexLabel,
  numberColWidth,
  onToggleDetails,
  statusLabel,
  primaryText,
  primaryTooltip,
  secondaryText,
  secondaryTooltip,
  chipChannel,
  chipNode,
  chipTask,
  toolName,
  resultOk,
}: {
  message: ChatMessage;
  indexLabel: React.ReactNode;
  numberColWidth: string;
  onToggleDetails?: () => void;
  statusLabel?: string;
  primaryText?: string;
  primaryTooltip?: string;
  secondaryText?: string;
  secondaryTooltip?: string;
  chipChannel: string;
  chipNode?: string;
  chipTask?: string;
  toolName?: string;
  resultOk?: boolean;
}) {
  const theme = useTheme();
  const color = channelColor(m.channel);
  const [expanded, setExpanded] = useState(false);

  const baseAccent = (() => {
    switch (color) {
      case "primary":
        return theme.palette.primary.main;
      case "secondary":
        return theme.palette.secondary.main;
      case "error":
        return theme.palette.error.main;
      case "info":
        return theme.palette.info.main;
      case "success":
        return theme.palette.success.main;
      case "warning":
        return theme.palette.warning.main;
      default:
        return theme.palette.divider;
    }
  })();

  const accentMain =
    typeof resultOk !== "undefined" ? (resultOk ? theme.palette.success.main : theme.palette.error.main) : baseAccent;

  const hasResult = typeof resultOk !== "undefined";
  const baseIntensity = theme.palette.mode === "dark" ? 0.15 : 0.05;
  const tintedBg = alpha(accentMain, hasResult ? baseIntensity : baseIntensity * 0.35);
  const tintedHover = alpha(accentMain, hasResult ? baseIntensity + 0.06 : baseIntensity * 0.6);
  const borderColor = alpha(accentMain, hasResult ? 0.2 : 0.12);
  const hoverBorderColor = alpha(accentMain, hasResult ? 0.28 : 0.18);
  const accentBarColor = alpha(accentMain, hasResult ? 0.5 : 0.28);
  const transitionValue = theme.transitions.create(["background-color", "border-color", "box-shadow", "transform"], {
    duration: theme.transitions.duration.shorter,
  });

  const stepBubbleBg = alpha(accentMain, theme.palette.mode === "dark" ? 0.2 : 0.08);
  const stepBubbleFg = theme.palette.mode === "dark" ? theme.palette.getContrastText(stepBubbleBg) : accentMain;

  const derivedStatus =
    statusLabel ??
    (typeof resultOk === "boolean" ? (resultOk ? "ok" : "error") : resultOk === undefined ? undefined : undefined);
  const statusChipColor =
    typeof resultOk === "boolean"
      ? resultOk
        ? "success"
        : "error"
      : derivedStatus === "pending"
        ? "warning"
        : "default";

  const toggleExpanded = () => setExpanded((prev) => !prev);

  return (
    <ListItemButton
      component="div"
      onClick={toggleExpanded}
      disableRipple
      disableTouchRipple
      sx={{
        borderRadius: 2,
        px: 1.4,
        py: 0.9,
        display: "flex",
        alignItems: "stretch",
        gap: 1,
        position: "relative",
        overflow: "hidden",
        backgroundColor: tintedBg,
        border: `1px solid ${borderColor}`,
        boxShadow: hasResult ? theme.shadows[1] : theme.shadows[0],
        transition: transitionValue,
        "&::before": {
          content: '""',
          position: "absolute",
          top: 0,
          bottom: 0,
          left: 0,
          width: 3,
          bgcolor: accentBarColor,
        },
        "&:hover": {
          backgroundColor: tintedHover,
          borderColor: hoverBorderColor,
          transform: "translateY(-1px)",
          boxShadow: hasResult ? theme.shadows[3] : theme.shadows[1],
        },
      }}
    >
      <Box
        sx={{
          flexShrink: 0,
          minWidth: numberColWidth || "24px",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <Box
          sx={{
            width: 26,
            height: 26,
            borderRadius: "999px",
            backgroundColor: stepBubbleBg,
            color: stepBubbleFg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 500,
            fontVariantNumeric: "tabular-nums",
            fontSize: "0.8rem",
            border: `1px solid ${alpha(accentMain, 0.35)}`,
            boxShadow: theme.shadows[1],
          }}
        >
          {indexLabel}
        </Box>
      </Box>

      <Stack spacing={0.75} sx={{ minWidth: 0, flex: 1, pr: 1 }}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" sx={{ opacity: 0.95 }}>
          <Chip label={chipChannel} size="small" variant="outlined" color={color} sx={{ fontWeight: 600 }} />
          {toolName && (
            <Chip
              icon={<TerminalIcon sx={{ fontSize: 16 }} />}
              label={toolName}
              size="small"
              variant="outlined"
              sx={{
                backgroundColor: alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.2 : 0.08),
              }}
            />
          )}
          {!toolName && chipNode && <Chip label={chipNode} size="small" variant="outlined" />}
          {derivedStatus && (
            <Chip
              label={
                derivedStatus === "pending" ? (theme.palette.mode === "dark" ? "pending" : "pending") : derivedStatus
              }
              size="small"
              color={statusChipColor as "default" | "success" | "error" | "warning"}
              variant={statusChipColor === "default" ? "outlined" : "filled"}
              sx={{ fontWeight: 600, textTransform: "lowercase" }}
            />
          )}
        </Stack>

        {(primaryText || secondaryText) && (
          <Collapse in={expanded} timeout="auto" unmountOnExit sx={{ minWidth: 0 }}>
            <Stack direction="column" spacing={0.75} sx={{ minWidth: 0, pr: 1 }}>
              {chipTask && chipTask !== chipNode && (
                <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
                  <Chip label={chipTask} size="small" />
                </Stack>
              )}
              {primaryText && (
                <Tooltip title={primaryTooltip ?? ""} enterTouchDelay={0} disableHoverListener={!primaryTooltip}>
                  <Typography
                    variant="body2"
                    sx={{
                      minWidth: 0,
                      maxWidth: "100%",
                      fontWeight: 500,
                      color: theme.palette.text.primary,
                      whiteSpace: "nowrap",
                      textOverflow: "ellipsis",
                      overflow: "hidden",
                    }}
                  >
                    {primaryText}
                  </Typography>
                </Tooltip>
              )}
              {secondaryText && (
                <Tooltip title={secondaryTooltip ?? ""} enterTouchDelay={0} disableHoverListener={!secondaryTooltip}>
                  <Typography
                    variant="body2"
                    sx={{
                      minWidth: 0,
                      maxWidth: "100%",
                      color:
                        typeof resultOk === "undefined"
                          ? theme.palette.text.secondary
                          : resultOk
                            ? theme.palette.success.dark
                            : theme.palette.error.main,
                      fontWeight: resultOk === false ? 600 : 500,
                      whiteSpace: "nowrap",
                      textOverflow: "ellipsis",
                      overflow: "hidden",
                    }}
                  >
                    {secondaryText}
                  </Typography>
                </Tooltip>
              )}
            </Stack>
          </Collapse>
        )}
      </Stack>

      <Stack direction="row" spacing={0.25} alignItems="center" sx={{ flexShrink: 0, pr: 0.25 }}>
        {onToggleDetails && (
          <Tooltip title="Ouvrir les détails">
            <IconButton
              size="small"
              onClick={(event) => {
                event.stopPropagation();
                onToggleDetails();
              }}
            >
              <LaunchRoundedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Stack>
    </ListItemButton>
  );
}
