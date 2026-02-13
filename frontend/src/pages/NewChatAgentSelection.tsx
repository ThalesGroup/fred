import { Alert, Box, Skeleton, Typography, useTheme } from "@mui/material";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AnyAgent } from "../common/agent";
import { AgentTile } from "../components/chatbot/AgentTile";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { KeyCloakService } from "../security/KeycloakService";
import { useListAgentsAgenticV1AgentsGetQuery } from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

export function NewChatAgentSelection() {
  const { t } = useTranslation();
  const theme = useTheme();
  const username =
    KeyCloakService.GetUserGivenName?.() ||
    KeyCloakService.GetUserFullName?.() ||
    KeyCloakService.GetUserName?.() ||
    "";

  const { contactSupportLink } = useFrontendProperties();
  const {
    data: rawAgents,
    isLoading: agentLoading,
    isError: agentError,
  } = useListAgentsAgenticV1AgentsGetQuery(
    {},
    {
      refetchOnMountOrArgChange: true,
    },
  );

  const agents = useMemo<AnyAgent[]>(() => normalizeAgenticFlows(rawAgents), [rawAgents]);

  const enabledAgents = agents.filter((a) => a.enabled);

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

        {/* Your agents title */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "center" }}>
          <Typography variant="subtitle1" color="textSecondary">
            {/* Todo: use nickname */}
            {t("newChat.yourAgents")}
          </Typography>

          <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 2 }}>
            {/* Loading */}
            {agentLoading &&
              Array.from({ length: 9 }, (_, i) => (
                <Skeleton variant="rounded" key={i} sx={{ height: "76px", width: "200px" }} />
              ))}

            {/* Error message */}
            {agentError && (
              <Alert severity="error">
                {t("newChat.loadingAgentError")}
                {contactSupportLink && (
                  <>
                    {" "}
                    <Link to={contactSupportLink} target="_blank" style={{ color: theme.palette.primary.main }}>
                      {t("common.contactSupport")}
                    </Link>
                  </>
                )}
              </Alert>
            )}

            {/* Agent list */}
            {!agentLoading && !agentError && enabledAgents.map((agent) => <AgentTile key={agent.id} agent={agent} />)}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
