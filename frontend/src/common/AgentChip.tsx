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
  const ICON_GAP = 6; // distance between icon and text
  const ICON_BOX_W = ICON_SIZE + ICON_GAP; // mirrored on the right
  const CHIP_HEIGHT = 24;
  const PILL_RADIUS = 999;
  const SIDE_PAD = 8; // equal padding from chip borders (L & R)
  const NAME_MAX_W = 160; // cap; keep if you want ellipsis sooner

  return (
    <Chip
      variant="outlined"
      label={
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: `${ICON_BOX_W}px minmax(0, 1fr)`,
            alignItems: "center",
            columnGap: 0,
            minWidth: 0,
            px: `${SIDE_PAD}px`,
          }}
        >
          {/* Left icon track */}
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-start", width: ICON_BOX_W }}>
            <ChipIcon sx={{ fontSize: ICON_SIZE, color: chipColor }} />
          </Box>

          {/* Middle: flex-centered text to be *geometrically* centered */}
          <Box sx={{ display: "flex", justifyContent: "center", minWidth: 0 }}>
            <Typography
              variant="caption"
              fontWeight="medium"
              sx={{
                color: chipColor,
                lineHeight: "18px",
                letterSpacing: 0.2,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: NAME_MAX_W,
              }}
              title={agent.name}
            >
              {agent.name}
            </Typography>
          </Box>
        </Box>
      }
      sx={[
        {
          height: CHIP_HEIGHT,
          borderRadius: PILL_RADIUS,
          borderColor: chipColor,
          color: chipColor,
          boxShadow: "none",
          p: 0, // IMPORTANT: no root padding; we control side padding in the grid

          "& .MuiChip-label": {
            p: 0,
            display: "block",
            minWidth: 0,
          },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
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
