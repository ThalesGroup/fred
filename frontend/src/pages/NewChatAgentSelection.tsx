import { Alert, Box, Button, Chip, Skeleton, Stack, Typography, useTheme } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AnyAgent } from "../common/agent";
import { AgentTile } from "../components/chatbot/AgentTile";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { KeyCloakService } from "../security/KeycloakService";
import { useListAgentsAgenticV1AgentsGetQuery } from "../slices/agentic/agenticOpenApi";
import { useListTeamsKnowledgeFlowV1TeamsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowApiEnhancements";
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
  const { data: teams = [] } = useListTeamsKnowledgeFlowV1TeamsGetQuery();

  const agents = useMemo<AnyAgent[]>(() => normalizeAgenticFlows(rawAgents), [rawAgents]);
  const enabledAgents = useMemo(() => agents.filter((a) => a.enabled), [agents]);
  const teamScopedAgents = useMemo(() => enabledAgents.filter((a) => Boolean(a.team_id)), [enabledAgents]);
  const personalAgents = useMemo(() => enabledAgents.filter((a) => !a.team_id), [enabledAgents]);

  const teamsById = useMemo(
    () => Object.fromEntries((teams || []).map((team) => [team.id, team])),
    [teams],
  );
  const teamChoices = useMemo(() => {
    const counts = new Map<string, number>();
    for (const agent of teamScopedAgents) {
      const teamId = agent.team_id;
      if (!teamId) continue;
      counts.set(teamId, (counts.get(teamId) || 0) + 1);
    }

    return [...counts.entries()]
      .map(([id, agentCount]) => {
        const team = teamsById[id];
        return {
          id,
          name: team?.name || id,
          isMember: Boolean(team?.is_member),
          agentCount,
        };
      })
      .sort((a, b) => {
        if (a.isMember !== b.isMember) return a.isMember ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
  }, [teamScopedAgents, teamsById]);

  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedTeamId) {
      return;
    }
    if (teamChoices.some((team) => team.id === selectedTeamId)) {
      return;
    }
    setSelectedTeamId(null);
  }, [selectedTeamId, teamChoices]);

  const effectiveSelectedTeamId = selectedTeamId || (teamChoices.length === 1 ? teamChoices[0].id : null);
  const selectedTeam = useMemo(
    () => teamChoices.find((team) => team.id === effectiveSelectedTeamId) || null,
    [effectiveSelectedTeamId, teamChoices],
  );
  const visibleTeamAgents = useMemo(() => {
    if (teamChoices.length === 0) {
      return enabledAgents;
    }
    if (!effectiveSelectedTeamId) {
      return [];
    }
    return teamScopedAgents.filter((agent) => agent.team_id === effectiveSelectedTeamId);
  }, [effectiveSelectedTeamId, enabledAgents, teamChoices.length, teamScopedAgents]);
  const shouldGateTeamSelection = teamChoices.length > 1 && !effectiveSelectedTeamId;
  const showPersonalAgents = !shouldGateTeamSelection && teamChoices.length > 0 && personalAgents.length > 0;

  const handleTeamSelection = (teamId: string) => {
    setSelectedTeamId(teamId);
  };
  const isTeamSelected = (teamId: string) => effectiveSelectedTeamId === teamId;

  const visiblePersonalAgents = useMemo(
    () => (showPersonalAgents ? personalAgents : []),
    [showPersonalAgents, personalAgents],
  );

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

        {teamChoices.length > 0 && (
          <Box
            sx={{
              width: "100%",
              borderRadius: 2,
              border: "1px solid",
              borderColor: "divider",
              backgroundColor: "background.paper",
              p: 2,
              display: "flex",
              flexDirection: "column",
              gap: 1.5,
            }}
          >
            <Typography variant="subtitle1" color="textPrimary">
              {t("newChat.teamPromptTitle")}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {t("newChat.teamPromptSubtitle")}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {teamChoices.map((team) => (
                <Chip
                  key={team.id}
                  clickable
                  variant={isTeamSelected(team.id) ? "filled" : "outlined"}
                  color={isTeamSelected(team.id) ? "primary" : "default"}
                  onClick={() => handleTeamSelection(team.id)}
                  label={`${team.name} (${team.agentCount})`}
                />
              ))}
            </Stack>
            <Box>
              <Button component={Link} to="/teams" size="small">
                {t("newChat.browseTeams")}
              </Button>
            </Box>
            {shouldGateTeamSelection && (
              <Alert severity="info" sx={{ mt: 0.5 }}>
                {t("newChat.selectTeamToContinue")}
              </Alert>
            )}
          </Box>
        )}

        {/* Your agents title */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "center" }}>
          {!shouldGateTeamSelection && (
            <Typography variant="subtitle1" color="textSecondary">
              {selectedTeam ? t("newChat.teamAgentsTitle", { teamName: selectedTeam.name }) : t("newChat.yourAgents")}
            </Typography>
          )}

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
            {!agentLoading &&
              !agentError &&
              !shouldGateTeamSelection &&
              visibleTeamAgents.map((agent) => <AgentTile key={agent.id} agent={agent} />)}

            {!agentLoading && !agentError && !shouldGateTeamSelection && visibleTeamAgents.length === 0 && selectedTeam && (
              <Alert severity="warning">{t("newChat.noAgentsForTeam", { teamName: selectedTeam.name })}</Alert>
            )}
          </Box>

          {!agentLoading && !agentError && visiblePersonalAgents.length > 0 && (
            <>
              <Typography variant="subtitle1" color="textSecondary">
                {t("newChat.personalAgents")}
              </Typography>
              <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 2 }}>
                {visiblePersonalAgents.map((agent) => (
                  <AgentTile key={agent.id} agent={agent} />
                ))}
              </Box>
            </>
          )}
        </Box>
      </Box>
    </Box>
  );
}
