import React from "react";
import { Box, Chip, ListItemButton, Stack, Typography } from "@mui/material";
import type { Channel, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import TerminalIcon from "@mui/icons-material/Terminal";

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
  onClick,
  primaryText,
  chipChannel,
  chipNode,
  chipTask,
  toolName,
  resultOk,
}: {
  message: ChatMessage;
  indexLabel: React.ReactNode;
  numberColWidth: string;
  onClick: () => void;
  primaryText: string;
  chipChannel: string;
  chipNode?: string;
  chipTask?: string;
  toolName?: string;
  resultOk?: boolean;
}) {
  const color = channelColor(m.channel);

  return (
    <ListItemButton
      onClick={onClick}
      sx={{
        py: 0.9,
        display: "grid",
        gridTemplateColumns: `${numberColWidth} 1fr`, // number | content
        columnGap: 1,
        alignItems: "center",
        position: "relative",
        "&::before": {
          content: '""',
          display: "block",
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 2,
          bgcolor: (t) =>
            color === "default"
              ? t.palette.divider // or t.palette.grey[400]
              : t.palette[color].main,
          opacity: 0.35,
        },
        pl: 1.5,
      }}
    >
      {/* Number rail */}
      <Box
        sx={{
          textAlign: "right",
          pr: 1,
          color: "text.disabled",
          fontVariantNumeric: "tabular-nums",
          whiteSpace: "nowrap",
          fontFamily:
            "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
        }}
      >
        {indexLabel}
      </Box>

      {/* Content: chips left, text right */}
      <Box sx={{ minWidth: 0 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 0 }}>
          {/* Chips group (left, can wrap within its own box if needed) */}
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", alignItems: "center" }}>
            <Chip label={chipChannel} size="small" variant="outlined" color={color} />
            {chipNode && <Chip label={chipNode} size="small" />}
            {chipTask && <Chip label={chipTask} size="small" />}
            {toolName && (
              <Chip icon={<TerminalIcon sx={{ fontSize: 16 }} />} label={toolName} size="small" variant="outlined" />
            )}
            {m.channel === "tool_result" && typeof resultOk !== "undefined" && (
              <Chip
                label={resultOk ? "ok" : "error"}
                size="small"
                color={resultOk ? "success" : "error"}
                variant={resultOk ? "outlined" : "filled"}
              />
            )}
            {m.metadata?.agent_name && <Chip label={m.metadata.agent_name} size="small" variant="outlined" />}
          </Box>

          {/* Preview text (right, single line, ellipsis) */}
          <Typography variant="body2" noWrap sx={{ ml: "auto", minWidth: 0, flex: 1, textAlign: "right" }}>
            {primaryText}
          </Typography>
        </Stack>
      </Box>
    </ListItemButton>
  );
}
