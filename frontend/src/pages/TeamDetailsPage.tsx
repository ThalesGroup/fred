import { Avatar, Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { TeamAgentHub } from "../components/teamDetails/TeamAgentHub";
import { TeamAppsPage } from "../components/teamDetails/TeamAppsPage";
import { TeamMembersPage } from "../components/teamDetails/TeamMembersPage";
import { TeamSettingsPage } from "../components/teamDetails/TeamSettingsPage";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { capitalize } from "../utils/capitalize";

export function TeamDetailsPage() {
  const { t } = useTranslation();
  const { agentsNicknamePlural } = useFrontendProperties();

  const { teamId } = useParams<{ teamId: string }>();
  const { data: team } = useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery({ teamId: teamId || "" }, { skip: !teamId });

  // todo: handle loading
  // todo: handle error (404)

  const tabs: TabConfig[] = [
    {
      label: capitalize(agentsNicknamePlural || "..."),
      path: `/team/${teamId}/${agentsNicknamePlural}`,
      component: <TeamAgentHub />,
    },
    {
      label: t("teamDetails.tabs.resources"),
      path: `/team/${teamId}/resources`,
      component: (
        <Box>
          <Typography>Resources content for {team?.name || "..."}</Typography>
        </Box>
      ),
    },
    {
      label: t("teamDetails.tabs.apps"),
      path: `/team/${teamId}/apps`,
      component: <TeamAppsPage />,
    },
    {
      label: t("teamDetails.tabs.members"),
      path: `/team/${teamId}/members`,
      component: <TeamMembersPage />,
    },
    {
      label: t("teamDetails.tabs.settings"),
      path: `/team/${teamId}/settings`,
      component: <TeamSettingsPage team={team} />,
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
        contentContainerSx={{ flex: 1, overflow: "auto" }}
      />
    </Box>
  );
}
