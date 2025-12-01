// AgentChip.tsx (Consolidated: AgentChipWithIcon and AgentChipMini)

import { alpha, Box, Chip, SxProps, Theme, Typography, useTheme } from "@mui/material";
import { AgentColorHint, AnyAgent, getAgentVisuals } from "./agent";

// --- Configuration Constants ---

// Constants for the mini chip (Mini)
const CHIP_MINI_HEIGHT = 18; // ultra-compact
const PAD_X = 4; // left/right gutter (px)
const CORNER = 8; // small rounded, keeps legible silhouette
const FONT_SIZE = 10; // tiny but readable
const LETTER_SPACING = 0.2; // avoids cramped uppercase
const MAX_WIDTH = 96; // enough for ≤10 chars + ellipsis

// --- THEME COLOR MAPPING ---
// Maps the functional color hints to specific, high-contrast chart colors.
const THEME_COLOR_MAP = (theme: Theme): Record<AgentColorHint, string> => ({
  // Leaders: Use high-contrast purple
  leader: theme.palette.chart.purple,

  // Data/Knowledge: Mapped to chart.blue (Information/Context)
  data: theme.palette.chart.blue,

  // Execution/Tool: Mapped to chart.green (Action/Success)
  execution: theme.palette.chart.green, // NOTE: Changed back to green for execution to maximize color variation

  // Drafting/Content: Mapped to chart.orange (Creation/Drafting, high visibility)
  document: theme.palette.chart.blue, // NOTE: Changed back to orange for drafting

  // Fallback/General: Mapped to chart.secondary
  general: theme.palette.chart.blue,
});

// --- Component Props and Definition ---

interface AgentChipProps {
  agent: AnyAgent | null | undefined;
  align?: "center" | "right";
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
export const AgentChipWithIcon = ({ agent, sx }: AgentChipProps) => {
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
          title={agent.name}
        >
          {agent.name}
        </Typography>

        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            minWidth: 0,
            maxWidth: ROLE_MAX_W,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            lineHeight: 1.1,
            textTransform: "none",
            textAlign: "center",
            fontSize: "12.5px",
          }}
          title={agent.tuning.role}
        >
          {agent.tuning.role}
        </Typography>
      </Box>
    </Box>
  );
};

// --- AgentChipMini Component ---

interface AgentChipMiniProps {
  agent: AnyAgent | null | undefined;
  sx?: SxProps;
  /** If true, add a  subtle hover bg without increasing size */
  subtleHover?: boolean;
}

export const AgentChipMini = ({ agent, sx, subtleHover = true }: AgentChipMiniProps) => {
  if (!agent) return null;

  const theme = useTheme();
  const { colorHint } = getAgentVisuals(agent);
  const chipColor = THEME_COLOR_MAP(theme)[colorHint];
  const initial = agent.name?.charAt(0)?.toUpperCase() ?? "?";

  return (
    <Chip
      variant="outlined"
      size="small"
      // No icon for mini; pure text
      label={
        <Box
          sx={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minWidth: 0,
            px: `${PAD_X}px`,
          }}
        >
          <Typography
            // overline is typically tall; we use caption with tuned size for tighter line-box
            variant="caption"
            sx={{
              color: chipColor,
              fontSize: `${FONT_SIZE}px`,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: `${LETTER_SPACING}px`,
              lineHeight: 1, // tight vertical rhythm
              whiteSpace: "nowrap",
              maxWidth: "100%",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={agent.name} // full name on hover if truncated
          >
            {initial}
          </Typography>
        </Box>
      }
      sx={[
        (t) => ({
          // Width: auto but capped; stays compact while allowing a bit of growth
          maxWidth: MAX_WIDTH,
          minWidth: 0,
          height: CHIP_MINI_HEIGHT,
          borderRadius: CORNER,
          borderColor: chipColor,
          color: chipColor,
          // Keep the root dense: remove default paddings around label
          p: 0,

          // Make sure the internal label is flex and has zero padding
          "& .MuiChip-label": {
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            p: 0.3,
            minWidth: 0,
          },

          // Optional: very subtle hover tint that respects the current mode
          ...(subtleHover && {
            transition: "background-color 120ms ease",
            "&:hover": {
              backgroundColor: t.palette.mode === "dark" ? alpha(chipColor, 0.08) : alpha(chipColor, 0.06),
            },
          }),
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
  );
};
