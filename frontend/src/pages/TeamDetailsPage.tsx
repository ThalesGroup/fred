import { Avatar, Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { TeamAgentHub } from "../components/teamDetails/teamAgentHub";
import { TeamAppsPage } from "../components/teamDetails/TeamAppsPage";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { useListGroupsKnowledgeFlowV1GroupsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export function TeamDetailsPage() {
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  const { agentsNicknamePlural } = useFrontendProperties();

  const {
    data: groups = [],
    isLoading,
    isError,
  } = useListGroupsKnowledgeFlowV1GroupsGetQuery({
    limit: 10000,
    offset: 0,
    memberOnly: false,
  });

  const team = groups.find((g) => g.id === teamId);

  if (isLoading) {
    return (
      <Box sx={{ px: 3, py: 2 }}>
        <Typography variant="body2" color="textSecondary">
          {t("common.loading")}
        </Typography>
      </Box>
    );
  }

  if (isError || !team) {
    return (
      <Box sx={{ px: 3, py: 2 }}>
        <Typography variant="body2" color="error">
          {t("common.error")}
        </Typography>
      </Box>
    );
  }

  const tabs: TabConfig[] = [
    {
      label: agentsNicknamePlural,
      path: `/team/${team.id}/${agentsNicknamePlural}`,
      component: <TeamAgentHub />,
    },
    {
      label: t("teamDetails.tabs.resources"),
      path: `/team/${team.id}/resources`,
      component: (
        <Box>
          <Typography>Resources content for {team.name}</Typography>
        </Box>
      ),
    },
    {
      label: t("teamDetails.tabs.apps"),
      path: `/team/${team.id}/apps`,
      component: <TeamAppsPage />,
    },
    {
      label: t("teamDetails.tabs.members"),
      path: `/team/${team.id}/members`,
      component: (
        <Box>
          <Typography>Members content for {team.name}</Typography>
        </Box>
      ),
    },
    {
      label: t("teamDetails.tabs.settings"),
      path: `/team/${team.id}/settings`,
      component: (
        <Box>
          <Typography>Settings content for {team.name}</Typography>
        </Box>
      ),
    },
  ];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "stretch" }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 3, py: 2 }}>
        {/* Avatar banner */}
        <Avatar variant="rounded" src={team.banner_image_url} sx={{ height: "3.5rem", width: "3.5rem" }} />

        {/* Title and description */}
        <Box sx={{ display: "flex", flexDirection: "column" }}>
          <Typography variant="h6">{team.name}</Typography>
          <Typography variant="body2" color="textSecondary">
            {team.description}
          </Typography>
        </Box>
      </Box>

      {/* Tabs */}
      <NavigationTabs tabs={tabs} tabsContainerSx={{ px: 2, pb: 1 }} />
    </Box>
  );
}
