import { Stack, Typography } from "@mui/material";
import { memo } from "react";
import { useTranslation } from "react-i18next";
import { McpServerRef, useListMcpServersAgenticV1AgentsMcpServersGetQuery } from "../../slices/agentic/agenticOpenApi";
import { AgentOptionSelectionCard } from "./AgentOptionSelectionCard";

export interface AgentToolsSelectionProps {
  mcpServerRefs: McpServerRef[];
  onMcpServerRefsChange: (newMcpServerRefs: McpServerRef[]) => void;
}

export const AgentToolsSelection = memo(function AgentToolsSelection({
  mcpServerRefs,
  onMcpServerRefsChange,
}: AgentToolsSelectionProps) {
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
    <>
      <Typography variant="subtitle2">{t("agentHub.toolsSelection.title")}</Typography>

      <Stack spacing={0.75}>
        {mcpServersData.map((conf, index) => {
          const isEnabled = conf.enabled !== false;
          if (!isEnabled) {
            return null;
          }
          return (
            <AgentOptionSelectionCard
              key={index}
              name={t(conf.name)}
              description={t(conf.description)}
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
    </>
  );
});
