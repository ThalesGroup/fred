import { Box, Typography } from "@mui/material";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../common/agent";
import { AgentTile } from "../components/chatbot/AgentTile";
import { KeyCloakService } from "../security/KeycloakService";
import { useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery } from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

export function NewChatAgentSelection() {
  const { t } = useTranslation();
  const username =
    KeyCloakService.GetUserGivenName?.() ||
    KeyCloakService.GetUserFullName?.() ||
    KeyCloakService.GetUserName?.() ||
    "";

  const { data: rawAgents } = useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
  });

  const agents = useMemo<AnyAgent[]>(() => normalizeAgenticFlows(rawAgents), [rawAgents]);

  return (
    <Box sx={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          maxWidth: "804px",
          gap: 4,
        }}
      >
        <Typography variant="h5" color="textPrimary">
          {t("newChat.selectAgentTitle", { userName: username })}
        </Typography>

        {/* Your agents */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "center" }}>
          <Typography variant="subtitle1" color="textSecondary">
            {/* Todo: use nickname */}
            {t("newChat.yourAgents")}
          </Typography>

          <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 2 }}>
            {agents.map((agent) => (
              <AgentTile key={agent.name} agent={agent} />
            ))}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
