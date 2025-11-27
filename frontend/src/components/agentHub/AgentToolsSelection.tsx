import InfoIcon from "@mui/icons-material/Info";
import { Card, Stack, Switch, Tooltip, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import {
  McpServerConfiguration,
  McpServerRef,
  useListMcpServersAgenticV1AgentsMcpServersGetQuery,
} from "../../slices/agentic/agenticOpenApi";

export interface AgentToolsSelectionProps {
  mcpServerRefs: McpServerRef[];
  onMcpServerRefsChange: (newMcpServerRefs: McpServerRef[]) => void;
}

export function AgentToolsSelection({ mcpServerRefs, onMcpServerRefsChange }: AgentToolsSelectionProps) {
  const { t } = useTranslation();
  const { data: mcpServersData, isFetching: isFetchingMcpServers } =
    useListMcpServersAgenticV1AgentsMcpServersGetQuery();

  if (isFetchingMcpServers) {
    return <div>Loading tools...</div>;
  }

  if (!mcpServersData || mcpServersData.length === 0) {
    return <div>No tools available.</div>;
  }

  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{t("agentHub.toolsSelection.title")}</Typography>

      <Stack spacing={1}>
        {mcpServersData.map((conf, index) => {
          if (conf.enabled === false) {
            return null;
          }
          return (
            <AgentToolSelectionCard
              key={index}
              conf={conf}
              selected={mcpServerRefs.some((ref) => ref.id === conf.id)}
              onSelectedChange={(selected) => {
                if (selected) {
                  onMcpServerRefsChange([...mcpServerRefs, { id: conf.id }]);
                } else {
                  onMcpServerRefsChange(mcpServerRefs.filter((ref) => ref.id !== conf.id));
                }
              }}
            />
          );
        })}
      </Stack>
    </Stack>
  );
}

export interface AgentToolSelectionCardProps {
  conf: McpServerConfiguration;
  selected: boolean;
  onSelectedChange: (selected: boolean) => void;
}

export function AgentToolSelectionCard({ conf, selected, onSelectedChange }: AgentToolSelectionCardProps) {
  const { t } = useTranslation();

  return (
    <Card sx={{ padding: 0.5 }}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Switch checked={selected} onChange={(event) => onSelectedChange(event.target.checked)} />
        <Typography>{t(conf.name)}</Typography>
        {conf.description && (
          <Tooltip title={t(conf.description)} enterTouchDelay={0}>
            <InfoIcon />
          </Tooltip>
        )}
      </Stack>
    </Card>
  );
}
