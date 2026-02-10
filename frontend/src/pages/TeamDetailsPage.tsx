import { Avatar, Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { TeamAgentHub } from "../components/teamDetails/TeamAgentHub";
import { TeamAppsPage } from "../components/teamDetails/TeamAppsPage";
import { TeamDocumentsLibrary } from "../components/teamDetails/TeamDocumentsLibrary";
import { TeamMembersPage } from "../components/teamDetails/TeamMembersPage";
import { TeamSettingsPage } from "../components/teamDetails/TeamSettingsPage";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery } from "../slices/knowledgeFlow/knowledgeFlowApiEnhancements";
import { capitalize } from "../utils/capitalize";

export function TeamDetailsPage() {
  const { t } = useTranslation();
  const { agentsNicknamePlural } = useFrontendProperties();

  const { teamId } = useParams<{ teamId: string }>();
  const { data: team, isLoading } = useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery(
    { teamId: teamId || "" },
    { skip: !teamId },
  );
  // todo: handle error (404)

  if (teamId === undefined) {
    // Should never happen
    return <>need a team id in the url</>;
  }

  const memberTab: TabConfig = {
    label: t("teamDetails.tabs.members"),
    path: `/team/${teamId}/members`,
    component: <TeamMembersPage teamId={teamId} permissions={team?.permissions} />,
  };

  const settingTab: TabConfig = {
    label: t("teamDetails.tabs.settings"),
    path: `/team/${teamId}/settings`,
    component: <TeamSettingsPage team={team} />,
  };

  const tabs: TabConfig[] = [
    {
      label: capitalize(agentsNicknamePlural || "..."),
      path: `/team/${teamId}/${agentsNicknamePlural}`,
      component: <TeamAgentHub teamId={teamId} canCreateAgents={team?.permissions?.includes("can_update_agents")} />,
    },
    {
      label: t("teamDetails.tabs.resources"),
      path: `/team/${teamId}/resources`,
      component: (
        <TeamDocumentsLibrary teamId={teamId} canCreateTag={team?.permissions?.includes("can_update_resources")} />
      ),
    },
    {
      label: t("teamDetails.tabs.apps"),
      path: `/team/${teamId}/apps`,
      component: <TeamAppsPage />,
    },
    ...(team?.permissions?.includes("can_read_members") ? [memberTab] : []),
    ...(team?.permissions?.includes("can_update_info") ? [settingTab] : []),
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
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 3, py: 2 }}>
        {/* Avatar banner */}
        <Avatar variant="rounded" src={team?.banner_image_url || ""} sx={{ height: "3.5rem", width: "3.5rem" }} />

        {/* Title and description */}
        <Box sx={{ display: "flex", flexDirection: "column" }}>
          <Typography variant="h6">{team?.name}</Typography>
          <Typography
            variant="body2"
            color="textSecondary"
            sx={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 2,
              maxWidth: "90ch",
            }}
          >
            {team?.description}
          </Typography>
        </Box>
      </Box>

      {/* Tabs */}
      <NavigationTabs
        tabs={tabs}
        tabsContainerSx={{ px: 2, pb: 1 }}
        contentContainerSx={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", minHeight: 0 }}
        isLoading={isLoading}
      />
    </Box>
  );
}
