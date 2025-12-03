import HttpIcon from "@mui/icons-material/Http";
import TerminalRounded from "@mui/icons-material/TerminalRounded";
import { Card, Chip, Stack, Switch, Typography } from "@mui/material";
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
    useListMcpServersAgenticV1AgentsMcpServersGetQuery(undefined, {
      refetchOnMountOrArgChange: true,
      refetchOnFocus: true,
      refetchOnReconnect: true,
    });

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
              selected={mcpServerRefs.some((ref) => ref.name === conf.id)}
              onSelectedChange={(selected) => {
                if (selected) {
                  onMcpServerRefsChange([...mcpServerRefs, { name: conf.id }]);
                } else {
                  onMcpServerRefsChange(mcpServerRefs.filter((ref) => ref.name !== conf.id));
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
  const transport = (conf.transport || "streamable_http").toLowerCase();
  const isStdio = transport === "stdio";
  const transportLabel = isStdio
    ? t("agentHub.fields.mcp_server.transport_local", "Local process")
    : t("agentHub.fields.mcp_server.transport_http", "HTTP endpoint");
  const connectionDetail =
    transport === "streamable_http"
      ? conf.url || "—"
      : [conf.command, ...(conf.args || [])].filter(Boolean).join(" ") || "—";

  return (
    <Card
      sx={{
        padding: 1.25,
        borderColor: selected ? "primary.main" : "divider",
        boxShadow: selected ? 2 : 0,
      }}
      variant="outlined"
    >
      <Stack spacing={0.75}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Switch checked={selected} onChange={(event) => onSelectedChange(event.target.checked)} />
          <Stack spacing={0.25} flex={1}>
            <Typography fontWeight={600}>{t(conf.name)}</Typography>
            {conf.description && (
              <Typography variant="body2" color="text.secondary">
                {t(conf.description)}
              </Typography>
            )}
          </Stack>
          <Chip
            label={transportLabel}
            icon={isStdio ? <TerminalRounded fontSize="small" /> : <HttpIcon fontSize="small" />}
            color={isStdio ? "secondary" : "primary"}
            variant="outlined"
            size="small"
          />
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center" sx={{ marginLeft: "44px" }}>
          <Typography variant="caption" color="text.secondary">
            {isStdio ? t("agentHub.fields.mcp_server.command", "Command") : t("agentHub.fields.mcp_server.url")}
          </Typography>
          <Typography
            variant="body2"
            color="text.primary"
            sx={{
              fontFamily: "'JetBrains Mono', 'Fira Code', 'Menlo', 'Roboto Mono', monospace",
              backgroundColor: "action.hover",
              px: 1,
              py: 0.5,
              borderRadius: 1,
            }}
          >
            {connectionDetail}
          </Typography>
        </Stack>
      </Stack>
    </Card>
  );
}
