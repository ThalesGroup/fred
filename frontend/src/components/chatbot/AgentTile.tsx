import { Box, styled, Typography, useTheme } from "@mui/material";
import Paper from "@mui/material/Paper/Paper";
import { AnyAgent, getAgentVisuals } from "../../common/agent";
import { THEME_COLOR_MAP } from "../../common/AgentChip";
import InvisibleLink from "../InvisibleLink";

const HoverBox = styled(Box)<{ agentColor: string }>(({ theme, agentColor }) => ({
  "&:hover": {
    backgroundColor: theme.palette.action.hover,
    outline: `1px solid ${agentColor}`,
  },
}));

export interface AgentTileProps {
  agent: AnyAgent;
}

export function AgentTile({ agent }: AgentTileProps) {
  const { Icon: AgentIcon, colorHint } = getAgentVisuals(agent);
  const theme = useTheme();
  const agentColor = THEME_COLOR_MAP(theme)[colorHint];

  return (
    <InvisibleLink to={`/new-chat/${encodeURIComponent(agent.id)}`}>
      <Paper
        elevation={2}
        sx={{
          borderRadius: 2,
          userSelect: "none",
        }}
      >
        <HoverBox
          agentColor={agentColor}
          sx={{
            borderRadius: 2,
            display: "flex",
            alignItems: "center",
            pr: 2,
            pl: 2,
            gap: 1.5,
            py: 2,
            width: "240px",
            height: "100%",
          }}
        >
          {/* Icon */}
          <AgentIcon sx={{ color: agentColor, width: 28 }} />

          {/* Name + role */}
          <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
            <Typography
              variant="body1"
              color="textPrimary"
              sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {agent.name}
            </Typography>
            <Typography
              variant="body2"
              color="textSecondary"
              sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {agent.tuning?.role}
            </Typography>
          </Box>
        </HoverBox>
      </Paper>
    </InvisibleLink>
  );
}
