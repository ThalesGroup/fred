import { Alert, Box, Skeleton, styled, Typography, useTheme } from "@mui/material";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AnyAgent } from "../common/agent";
import { AgentTile } from "../components/chatbot/AgentTile";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { KeyCloakService } from "../security/KeycloakService";
import { useListAgentsAgenticV1AgentsGetQuery } from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

const AgentGrid = styled(Box)({
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
  gap: 16,
  width: "100%",
});

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
  const enabledAgents = useMemo(() => agents.filter((a) => a.enabled), [agents]);
  const teamScopedAgents = useMemo(
    () =>
      enabledAgents
        .filter((a) => Boolean(a.team_id))
        .sort((a, b) => (a.team_id ?? "").localeCompare(b.team_id ?? "") || a.name.localeCompare(b.name)),
    [enabledAgents],
  );
  const personalAgents = useMemo(() => enabledAgents.filter((a) => !a.team_id), [enabledAgents]);

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
          width: "100%",
          px: 2,
        }}
      >
        <Typography variant="h5" color="textPrimary">
          {t("newChat.selectAgentTitle", { userName: username })}
        </Typography>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, width: "100%" }}>
          {/* Loading */}
          {agentLoading && (
            <AgentGrid>
              {Array.from({ length: 9 }, (_, i) => (
                <Skeleton variant="rounded" key={i} sx={{ height: "76px" }} />
              ))}
            </AgentGrid>
          )}

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

          {/* Personal agents */}
          {!agentLoading && !agentError && personalAgents.length > 0 && (
            <>
              <Typography variant="subtitle1" color="textSecondary" sx={{ textAlign: "center" }}>
                {t("newChat.personalAgents")}
              </Typography>
              <AgentGrid>
                {personalAgents.map((agent) => (
                  <AgentTile key={agent.id} agent={agent} />
                ))}
              </AgentGrid>
            </>
          )}

          {/* Team agents */}
          {!agentLoading && !agentError && teamScopedAgents.length > 0 && (
            <>
              <Typography variant="subtitle1" color="textSecondary" sx={{ textAlign: "center" }}>
                {t("newChat.teamAgents")}
              </Typography>
              <AgentGrid>
                {teamScopedAgents.map((agent) => (
                  <AgentTile key={agent.id} agent={agent} />
                ))}
              </AgentGrid>
            </>
          )}
        </Box>
      </Box>
    </Box>
  );
}
