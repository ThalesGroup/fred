// AgentChip.tsx (Consolidated: AgentChipWithIcon and AgentChipMini)

import { Box, SxProps, Theme, Typography, useTheme } from "@mui/material";
import { forwardRef, type ForwardRefRenderFunction } from "react";
import { AgentColorHint, AnyAgent, getAgentVisuals } from "./agent";

// --- Configuration Constants ---

const LETTER_SPACING = 0.2; // avoids cramped uppercase

// --- THEME COLOR MAPPING ---
// Maps the functional color hints to specific, high-contrast chart colors.
const THEME_COLOR_MAP = (theme: Theme): Record<AgentColorHint, string> => ({
  // Leaders: Use high-contrast purple
  leader: theme.palette.secondary.main,

  // Data/Knowledge: Mapped to chart.blue (Information/Context)
  data: theme.palette.secondary.main,

  // Execution/Tool: Mapped to chart.green (Action/Success)
  execution: theme.palette.secondary.main,

  // Drafting/Content: Mapped to chart.orange (Creation/Drafting, high visibility)
  document: theme.palette.secondary.main,

  // Fallback/General: Mapped to chart.secondary
  general: theme.palette.secondary.main,
});

// --- Component Props and Definition ---

interface AgentChipProps {
  agent: AnyAgent | null | undefined;
  align?: "center" | "right";
  disableTitles?: boolean;
  sx?: SxProps;
}

/**
 * AgentChipWithIcon — Symmetric layout (icon left, name visually centered).
 * Fred rationale:
 * - We don't use the Chip's `icon` slot. Instead we render a 3-column grid
 *   so the middle column (name) is *visually centered* between chip borders.
 * - Right spacer mirrors the icon column width to avoid lopsided spacing.
 * - Chip width is intrinsic: no fixed min/max width unless you cap it.
 * - All colors come from theme tokens (mode-safe).
 */
export const AgentChipWithIcon = ({ agent, disableTitles = false, sx }: AgentChipProps) => {
  if (!agent) return null;

  const theme = useTheme();
  const { Icon: ChipIcon, colorHint } = getAgentVisuals(agent);
  const chipColor = THEME_COLOR_MAP(theme)[colorHint];

  // Visual constants
  const ICON_SIZE = 14;
  const NAME_MAX_W = 200; // allow a bit more breathing room
  const ROLE_MAX_W = 260;
  const GAP_X = 0.75;
  const ICON_PAD = ICON_SIZE + 6;

  return (
    <Box
      sx={[
        {
          position: "relative",
          display: "inline-flex",
          alignItems: "center",
          gap: `${GAP_X}rem`,
          textAlign: "center",
          minWidth: 0,
          py: 0.15,
          pl: `${ICON_PAD}px`,
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <ChipIcon
        sx={{
          fontSize: ICON_SIZE,
          color: chipColor,
          flexShrink: 0,
          display: "block",
          position: "absolute",
          left: 0,
          top: "50%",
          transform: "translateY(-50%)",
        }}
      />

      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: `${GAP_X}rem`,
          minWidth: 0,
          flexShrink: 1,
          justifyContent: "center",
          textAlign: "center",
        }}
      >
        <Typography
          variant="body1"
          fontWeight={700}
          sx={{
            color: chipColor,
            lineHeight: 1.1,
            letterSpacing: 0.2,
            fontSize: "14px",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: NAME_MAX_W,
            textAlign: "center",
          }}
          title={disableTitles ? undefined : agent.name}
        >
          {agent.name}
        </Typography>
      </Box>
    </Box>
  );
};

// --- AgentChipMini Component ---

interface AgentChipMiniProps {
  agent: AnyAgent | null | undefined;
  sx?: SxProps;
}

const AgentChipMiniBase: ForwardRefRenderFunction<HTMLDivElement, AgentChipMiniProps> = ({ agent, sx }, ref) => {
  if (!agent) return null;

  const theme = useTheme();
  const { colorHint } = getAgentVisuals(agent);
  const chipColor = THEME_COLOR_MAP(theme)[colorHint];

  return (
    <Typography
      ref={ref}
      variant="body1"
      fontWeight={700}
      title={agent.name}
      sx={[
        () => ({
          color: chipColor,
          lineHeight: 1.2,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          maxWidth: 180,
          letterSpacing: `${LETTER_SPACING}px`,
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {agent.name}
    </Typography>
  );
};

export const AgentChipMini = forwardRef(AgentChipMiniBase);
