import { Box, Divider, Tooltip, TooltipProps, Typography, useTheme } from "@mui/material";
import { AnyAgent } from "./agent";

export type AgentTooltipProps = AgentTooltipContentProps &
  Omit<TooltipProps, "title"> & {
    title?: TooltipProps["title"];
  };

export function AgentTooltip({ agent, title, ...props }: AgentTooltipProps) {
  const defaultTitle = <AgentTooltipContent agent={agent} />;

  return <Tooltip title={title ?? defaultTitle} placement="right" arrow {...props} />;
}

export interface AgentTooltipContentProps {
  agent: AnyAgent;
}

export function AgentTooltipContent({ agent }: AgentTooltipContentProps) {
  const theme = useTheme();

  return (
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
          sx={{ fontStyle: "italic", mb: agent.tuning.description ? 0.25 : 0 }}
        >
          {agent.tuning.role}
        </Typography>
        {agent.tuning.description && (
          <Typography variant="body2" color="text.secondary">
            {agent.tuning.description}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
