import { Box, Collapse, Stack, Typography } from "@mui/material";
import { memo } from "react";
import { useTranslation } from "react-i18next";
import { McpServerRef, useListMcpServersAgenticV1AgentsMcpServersGetQuery } from "../../slices/agentic/agenticOpenApi";
import { AgentOptionSelectionCard } from "./AgentOptionSelectionCard";
import { TOOL_PARAMS_REGISTRY } from "./toolParams/toolParamsRegistry";

export interface AgentToolsSelectionProps {
  mcpServerRefs: McpServerRef[];
  onMcpServerRefsChange: (newMcpServerRefs: McpServerRef[]) => void;
  teamId?: string;
}

export const AgentToolsSelection = memo(function AgentToolsSelection({
  mcpServerRefs,
  onMcpServerRefsChange,
  teamId,
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
          const registryEntry = tool.provider ? TOOL_PARAMS_REGISTRY[tool.provider] : undefined;
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
              {registryEntry && (
                <Collapse in={isSelected} unmountOnExit>
                  <Box sx={{ px: 1.25, pb: 1 }}>
                    {(() => {
                      const currentRef = mcpServerRefs.find((ref) => ref.id === tool.id);
                      const currentParams = currentRef?.params ?? registryEntry.defaultParams;
                      return registryEntry.render(
                        currentParams,
                        (updatedParams) => {
                          onMcpServerRefsChange(
                            mcpServerRefs.map((ref) =>
                              ref.id === tool.id
                                ? {
                                    ...ref,
                                    params: {
                                      ...(updatedParams as object),
                                      provider: registryEntry.provider,
                                    } as McpServerRef["params"],
                                  }
                                : ref,
                            ),
                          );
                        },
                        teamId,
                      );
                    })()}
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
