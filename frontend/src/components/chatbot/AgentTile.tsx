import GroupsIcon from "@mui/icons-material/Groups";
import { Box, Paper, styled, Typography, useTheme } from "@mui/material";
import { AnyAgent, getAgentVisuals } from "../../common/agent";
import { THEME_COLOR_MAP } from "../../common/AgentChip";
import { useListTeamsQuery } from "../../slices/controlPlane/controlPlaneApi";
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
  const {
    // Icon: AgentIcon,
    colorHint,
  } = getAgentVisuals(agent);
  const theme = useTheme();
  const agentColor = THEME_COLOR_MAP(theme)[colorHint];

  const { data: teams } = useListTeamsQuery(); // (If multiples tiles are displayed, Redux RTK query should cache the teams, so this should not cause multiple requests)
  const teamName = agent.team_id ? teams?.find((t) => t.id === agent.team_id)?.name : undefined;

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
            width: "100%",
            height: "100%",
          }}
        >
          {/* Icon */}
          {/* Hide agent icon for now as user do not choose it */}
          {/* <AgentIcon sx={{ color: agentColor, width: 28 }} /> */}

          {/* Name + role + team */}
          <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1, gap: 0.5 }}>
            {teamName && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                <GroupsIcon sx={{ fontSize: "1rem", color: "text.secondary" }} />
                <Typography
                  variant="caption"
                  color="textSecondary"
                  sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {teamName}
                </Typography>
              </Box>
            )}
            <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, gap: 0.25 }}>
              <Typography
                variant="subtitle1"
                color="primary"
                sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "1.125rem" }}
              >
                {agent.name}
              </Typography>
              <Typography
                variant="body1"
                color="textSecondary"
                sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {agent.tuning?.role}
              </Typography>
            </Box>
          </Box>
        </HoverBox>
      </Paper>
    </InvisibleLink>
  );
}
