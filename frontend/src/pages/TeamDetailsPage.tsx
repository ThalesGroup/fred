import { Avatar, Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { TeamAgentHub } from "../components/teamDetails/teamAgentHub";
import { TeamAppsPage } from "../components/teamDetails/TeamAppsPage";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { GroupSummary } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

// todo: remove when we wire backend
const teams: GroupSummary[] = [
  {
    id: "0",
    is_private: true,
    name: "Development Team and More and Even Longer Name and Stuff",
    description:
      "Team responsible for software development. It includes frontend and backend developers. They work on building and maintaining the core features of our applications. The team collaborates closely with the design and QA teams to ensure high-quality deliverables. Today , the development team is focused on implementing new features and fixing bugs reported by users.",
    member_count: 12,
    banner_image_url: "https://www.bio.org/act-root/bio/assets/images/banner-default.png",
    owners: [
      { id: "u1", username: "Alice Johnson", first_name: "Alice", last_name: "Johnson" },
      { id: "u2", username: "Bob Smith", first_name: "Bob", last_name: "Smith" },
    ],
  },
  {
    id: "1",
    name: "Marketing Team",
    description:
      "Team responsible for marketing strategies. It focuses on promoting our products and services to increase brand awareness and drive sales.",
    member_count: 8,
    banner_image_url: "https://www.bio.org/act-root/bio/assets/images/banner-default.png",
    owners: [
      { id: "u3", username: "Charlie Brown", first_name: "Charlie", last_name: "Brown" },
      { id: "u4", username: "Diana Prince", first_name: "Diana", last_name: "Prince" },
    ],
  },
  {
    id: "2",
    name: "Design Team",
    description: "",
    member_count: 2,
    banner_image_url: "https://www.bio.org/act-root/bio/assets/images/banner-default.png",
    owners: [
      { id: "u3", username: "Charlie Brown", first_name: "Charlie", last_name: "Brown" },
      { id: "u4", username: "Diana Prince", first_name: "Diana", last_name: "Prince" },
    ],
  },
];

export function TeamDetailsPage() {
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  const { agentsNicknamePlural } = useFrontendProperties();

  // todo: get team from backend
  const team = teams[teamId];

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
      <NavigationTabs
        tabs={tabs}
        tabsContainerSx={{ px: 2, pb: 1 }}
        contentContainerSx={{ flex: 1, overflow: "auto" }}
      />
    </Box>
  );
}
