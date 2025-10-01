// Copyright Thales 2025
//
// Fred UI — AgentsList
//
// WHY this exists (Fred rationale):
// - In Fred, "agentic flows" are *entry points* to capabilities (planning, tools, MCP).
//   Users must be able to pick an agent *before* or *without* selecting a conversation.
// - This component stays stateless regarding sessions; it only exposes the selected agent
//   and an onSelect callback. Conversation concerns live elsewhere.
// - Kept small, testable, and memoized: avoids sidebar re-renders when sessions update.

import {
  Box,
  Divider,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Theme,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { memo, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../../../common/agent";
import { getAgentBadge } from "../../../utils/avatar";

// Public contract kept minimal on purpose:
// - agents: source of truth from backend
// - selected?: current agent (can be undefined when nothing picked yet)
// - onSelect: emits the full agent (not just name) to keep parent logic simple
export type AgentsListProps = {
  agents: AnyAgent[];
  selected?: AnyAgent | null;
  onSelect: (flow: AnyAgent) => void;
  // Optional: override item density if needed in other places (defaults to "dense")
  dense?: boolean;
};

const AgentsList = memo(function AgentsList({ agents, selected, onSelect, dense = true }: AgentsListProps) {
  const theme = useTheme<Theme>();
  const { t } = useTranslation();
  const selectedName = selected?.name;

  const items = useMemo(() => agents, [agents]);
  const handleClick = useCallback((flow: AnyAgent) => () => onSelect(flow), [onSelect]);

  return (
    <Box
      role="navigation"
      aria-label={t("settings.assistants")}
      sx={{
        // Fred: side surfaces come from theme; parent controls width/placement.
        backgroundColor: theme.palette.sidebar.background,
        color: theme.palette.text.primary,
        borderBottom: `1px solid ${theme.palette.divider}`,
        px: 2,
        py: 2.5,
      }}
    >
      <Typography variant="subtitle1" sx={{ mb: 2 }}>
        {t("settings.assistants")}
      </Typography>

      <List dense={dense} disablePadding>
        {items.map((agent) => {
          const isSelected = selectedName === agent.name;

          const tooltipContent = (
            <Box sx={{ maxWidth: 460 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.75 }}>
                {agent.name}
              </Typography>
              <Divider sx={{ opacity: 0.5, mb: 0.75 }} />
              <Box
                sx={{
                  pl: 1.25,
                  borderLeft: `2px solid ${theme.palette.divider}`,
                }}
              >
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ fontStyle: "italic", mb: agent.description ? 0.25 : 0 }}
                >
                  {agent.role}
                </Typography>
                {agent.description && (
                  <Typography variant="body2" color="text.secondary">
                    {agent.description}
                  </Typography>
                )}
              </Box>
            </Box>
          );

          return (
            <ListItem key={agent.name} disableGutters sx={{ mb: 0 }}>
              <Tooltip title={tooltipContent} placement="right" arrow>
                <ListItemButton
                  onClick={handleClick(agent)}
                  selected={isSelected}
                  sx={{
                    borderRadius: 1,
                    px: 1,
                    py: 0,
                    // Fred: selection/hover strictly via theme tokens
                    border: `1px solid ${isSelected ? theme.palette.primary.main : theme.palette.divider}`,
                    backgroundColor: isSelected ? theme.palette.sidebar.activeItem : "transparent",
                    "&:hover": {
                      backgroundColor: theme.palette.sidebar.hoverColor,
                    },
                  }}
                >
                  {/* Single source of avatar truth */}
                  <Box sx={{ mr: 1, lineHeight: 0 }}>{getAgentBadge(agent.name, agent.type === "leader")}</Box>

                  <ListItemText
                    primary={agent.name}
                    secondary={agent.role}
                    slotProps={{
                      primary: {
                        variant: "body2",
                        fontWeight: isSelected ? 600 : 500,
                        noWrap: true,
                        color: isSelected ? theme.palette.primary.main : theme.palette.text.primary,
                      },
                      secondary: {
                        variant: "caption",
                        color: theme.palette.text.secondary,
                        noWrap: true,
                      },
                    }}
                  />
                </ListItemButton>
              </Tooltip>
            </ListItem>
          );
        })}
      </List>

      {!selected && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, px: 1 }}>
          {t("settings.pickAssistantToStart")}
        </Typography>
      )}
    </Box>
  );
});

export default AgentsList;
