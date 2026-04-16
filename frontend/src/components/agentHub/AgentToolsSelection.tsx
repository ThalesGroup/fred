import { Box, Collapse, Stack, Typography } from "@mui/material";
import { memo } from "react";
import { useTranslation } from "react-i18next";
import { McpServerRef, useListMcpServersAgenticV1AgentsMcpServersGetQuery } from "../../slices/agentic/agenticOpenApi";
import { AgentOptionSelectionCard } from "./AgentOptionSelectionCard";
import { TOOL_PARAMS_REGISTRY } from "./toolParams/toolParamsRegistry";

export interface AgentToolsSelectionProps {
  mcpServerRefs: McpServerRef[];
  onMcpServerRefsChange: (newMcpServerRefs: McpServerRef[]) => void;
}

export const AgentToolsSelection = memo(function AgentToolsSelection({
  mcpServerRefs,
  onMcpServerRefsChange,
}: AgentToolsSelectionProps) {
  const { t } = useTranslation();
  const { data: tools, isLoading: isLoadingMcpServers } = useListMcpServersAgenticV1AgentsMcpServersGetQuery();
  const refIds = new Set(mcpServerRefs.map((ref) => ref.id));

  if (isLoadingMcpServers) {
    return <div>Loading tools...</div>;
  }

  if (!tools || tools.length === 0) {
    return <div>No tools available.</div>;
  }

  return (
    <>
      <Typography variant="subtitle2">{t("agentHub.toolsSelection.title")}</Typography>

      <Stack spacing={0.75}>
        {tools.map((tool, index) => {
          const isEnabled = tool.enabled !== false;
          if (!isEnabled) {
            return null;
          }
          const isSelected = refIds.has(tool.id);
          const ParamsComponent = TOOL_PARAMS_REGISTRY[tool.id];
          return (
            <Box key={index} sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <AgentOptionSelectionCard
                name={t(tool.name)}
                description={t(tool.description)}
                selected={isSelected}
                onSelectedChange={(selected) => {
                  if (selected) {
                    onMcpServerRefsChange([...mcpServerRefs, { id: tool.id }]);
                  } else {
                    onMcpServerRefsChange(mcpServerRefs.filter((ref) => ref.id !== tool.id));
                  }
                }}
              />
              {ParamsComponent && (
                <Collapse in={isSelected} unmountOnExit>
                  <Box sx={{ mt: 0.5, px: 1.25, pb: 0.75 }}>
                    <ParamsComponent params={{}} onParamsChange={() => {}} />
                  </Box>
                </Collapse>
              )}
            </Box>
          );
        })}
      </Stack>
    </>
  );
});
