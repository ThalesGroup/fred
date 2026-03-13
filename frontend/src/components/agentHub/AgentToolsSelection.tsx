import HttpIcon from "@mui/icons-material/Http";
import TerminalRounded from "@mui/icons-material/TerminalRounded";
import { Box, Divider, Stack, Switch, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { CatalogBadge } from "../../shared/ui/catalog/CatalogBadge";
import { CatalogCard } from "../../shared/ui/catalog/CatalogCard";
import { CatalogMetaRow } from "../../shared/ui/catalog/CatalogMetaRow";
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
  const { data: mcpServersData, isFetching: isFetchingMcpServers } = useListMcpServersAgenticV1AgentsMcpServersGetQuery(
    undefined,
    {
      refetchOnMountOrArgChange: true,
      refetchOnFocus: true,
      refetchOnReconnect: true,
    },
  );
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
  const isInprocess = transport === "inprocess";
  const isStdio = transport === "stdio";
  const sourceKind = isInprocess ? "local" : "mcp";
  const sourceLabel =
    sourceKind === "local"
      ? t("agentHub.fields.mcp_server.source_local", "Local")
      : t("agentHub.fields.mcp_server.source_mcp", "MCP");
  const transportLabel = isInprocess
    ? t("agentHub.fields.mcp_server.transport_inprocess", "Local capability (inprocess)")
    : isStdio
      ? t("agentHub.fields.mcp_server.transport_local", "stdio (local MCP)")
      : t("agentHub.fields.mcp_server.transport_http", "HTTP (MCP)");
  const connectionDetail = isInprocess
    ? conf.provider || "—"
    : transport === "streamable_http"
      ? conf.url || "—"
      : [conf.command, ...(conf.args || [])].filter(Boolean).join(" ") || "—";

  return (
    <CatalogCard selected={selected}>
      <Stack spacing={1} sx={{ p: 1.25 }}>
        <Stack direction="row" spacing={1} alignItems="flex-start">
          <Switch
            size="small"
            checked={selected}
            onChange={(event) => onSelectedChange(event.target.checked)}
            sx={{ mt: -0.25, ml: -0.5 }}
          />
          <Stack spacing={0.35} flex={1} sx={{ minWidth: 0 }}>
            <Typography fontWeight={700} variant="body2" sx={{ lineHeight: 1.2 }}>
              {t(conf.name)}
            </Typography>
            {conf.description && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  lineHeight: 1.25,
                }}
                title={t(conf.description)}
              >
                {t(conf.description)}
              </Typography>
            )}
          </Stack>
        </Stack>

        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ ml: { xs: 0, sm: "36px" } }}>
          <CatalogBadge
            label={sourceLabel}
            icon={sourceKind === "local" ? <TerminalRounded fontSize="small" /> : <HttpIcon fontSize="small" />}
            tone={sourceKind === "local" ? "secondary" : "primary"}
          />
          <CatalogBadge label={transportLabel} />
        </Stack>

        <Divider sx={{ ml: { xs: 0, sm: "36px" } }} />

        <Box sx={{ ml: { xs: 0, sm: "36px" }, minWidth: 0 }}>
          <CatalogMetaRow
            dense
            label={
              isInprocess
                ? t("agentHub.fields.mcp_server.provider", "Provider")
                : isStdio
                  ? t("agentHub.fields.mcp_server.command", "Command")
                  : t("agentHub.fields.mcp_server.url")
            }
            value={
              <Box
                component="span"
                title={connectionDetail}
                sx={{
                  display: "inline-block",
                  width: "100%",
                  fontFamily: isInprocess
                    ? "inherit"
                    : "'JetBrains Mono', 'Fira Code', 'Menlo', 'Roboto Mono', monospace",
                  backgroundColor: "action.hover",
                  px: 1,
                  py: 0.5,
                  borderRadius: 1,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  verticalAlign: "middle",
                }}
              >
                {connectionDetail}
              </Box>
            }
          />
        </Box>

        <Typography
          variant="caption"
          color={selected ? "primary.main" : "text.secondary"}
          sx={{ ml: { xs: 0, sm: "36px" }, fontWeight: selected ? 600 : 500 }}
        >
          {selected ? t("common.enabled", "Enabled") : t("common.disabled", "Disabled")}
        </Typography>
      </Stack>
    </CatalogCard>
  );
}
