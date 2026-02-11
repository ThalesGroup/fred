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
  const refIds = new Set(mcpServerRefs.map((ref) => ref.id));

  if (isFetchingMcpServers) {
    return <div>Loading tools...</div>;
  }

  if (!mcpServersData || mcpServersData.length === 0) {
    return <div>No tools available.</div>;
  }

  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{t("agentHub.toolsSelection.title")}</Typography>

      <Stack spacing={0.75}>
        {mcpServersData.map((conf, index) => {
          const isEnabled = conf.enabled !== false;
          if (!isEnabled) {
            return null;
          }
          return (
            <AgentToolSelectionCard
              key={index}
              conf={conf}
              selected={refIds.has(conf.id)}
              onSelectedChange={(selected) => {
                if (selected) {
                  onMcpServerRefsChange([...mcpServerRefs, { id: conf.id }]);
                } else {
                  onMcpServerRefsChange(
                    mcpServerRefs.filter((ref) => {
                      const refId = ref.id;
                      return refId !== conf.id;
                    }),
                  );
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
        padding: 1,
        borderColor: selected ? "primary.main" : "divider",
        boxShadow: selected ? 2 : 0,
      }}
      variant="outlined"
    >
      <Stack spacing={0.5}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Switch
            size="small"
            checked={selected}
            onChange={(event) => onSelectedChange(event.target.checked)}
          />
          <Stack spacing={0.25} flex={1}>
            <Typography fontWeight={600} variant="body2">
              {t(conf.name)}
            </Typography>
            {conf.description && (
              <Typography variant="caption" color="text.secondary">
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

        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ marginLeft: "36px" }}>
          <Typography variant="caption" color="text.secondary" sx={{ minWidth: 88 }}>
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
