import { Paper, Stack, Switch, Typography } from "@mui/material";
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
  const { data: mcpServersData, isLoading: isLoadingMcpServers } = useListMcpServersAgenticV1AgentsMcpServersGetQuery();
  const refIds = new Set(mcpServerRefs.map((ref) => ref.id));

  if (isLoadingMcpServers) {
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

  return (
    <Paper
      elevation={60}
      onClick={() => onSelectedChange(!selected)}
      sx={[
        {
          boxShadow: "none",
          border: "1px solid transparent",
          borderRadius: 2,
          cursor: "pointer",
        },
        !selected && {
          "&:hover": {
            borderColor: "text.secondary",
          },
        },
        selected && { borderColor: "primary.main" },
      ]}
    >
      <Stack spacing={1} sx={{ p: 1.25 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Switch
            size="small"
            checked={selected}
            onChange={(event) => {
              event.stopPropagation();
              onSelectedChange(event.target.checked);
            }}
            sx={{ mt: -0.25, ml: -0.5 }}
          />
          <Stack gap={0.5} flex={1} sx={{ minWidth: 0 }}>
            <Typography fontWeight={selected ? 500 : 400} variant="body2" sx={{ lineHeight: 1.2, userSelect: "none" }}>
              {t(conf.name)}
            </Typography>

            {/* Description */}
            {conf.description && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  userSelect: "none",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  lineHeight: 1.25,
                }}
              >
                {t(conf.description)}
              </Typography>
            )}
          </Stack>
        </Stack>
      </Stack>
    </Paper>
  );
}
