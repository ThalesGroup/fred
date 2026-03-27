import { Box } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { TeamAgentHub } from "../components/teamDetails/TeamAgentHub";
import { TeamAppsPage } from "../components/teamDetails/TeamAppsPage";
import { TeamDocumentsLibrary } from "../components/teamDetails/TeamDocumentsLibrary";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApi";
import { capitalize } from "../utils/capitalize";
import { KnowledgeHub } from "./KnowledgeHub.tsx";
import { AgentHub } from "./AgentHub.tsx";

export function TeamDetailsPage() {
  const { t } = useTranslation();
  const { agentsNicknamePlural } = useFrontendProperties();

  const { teamId } = useParams<{ teamId: string }>();
  const { data: team, isLoading } = useGetTeamQuery({ teamId: teamId !== "user" ? teamId : "" }, { skip: !teamId });
  // todo: handle error (404)

  if (teamId === undefined) {
    // Should never happen
    return <>need a team id in the url</>;
  }

  const tabs: TabConfig[] = [
    {
      label: capitalize(agentsNicknamePlural || "..."),
      path: `/team/${teamId}/${agentsNicknamePlural}`,
      component:
        teamId === "user" ? (
          <AgentHub />
        ) : (
          <TeamAgentHub teamId={teamId} canCreateAgents={team?.permissions?.includes("can_update_agents")} />
        ),
    },
    {
      label: t("teamDetails.tabs.resources"),
      path: `/team/${teamId}/resources`,
      component:
        teamId === "user" ? (
          <KnowledgeHub />
        ) : (
          <TeamDocumentsLibrary teamId={teamId} canCreateTag={team?.permissions?.includes("can_update_resources")} />
        ),
    },
    {
      label: t("teamDetails.tabs.apps"),
      path: `/team/${teamId}/apps`,
      component: <TeamAppsPage />,
    },
  ];

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "stretch",
        flex: 1,
        overflow: "hidden",
      }}
    >
      {/* Tabs */}
      <NavigationTabs
        tabs={tabs}
        contentContainerSx={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", minHeight: 0 }}
        isLoading={isLoading}
      />
    </Box>
  );
}
