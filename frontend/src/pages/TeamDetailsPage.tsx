import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery } from "../slices/agentic/agenticOpenApi";
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
    description:
      "Team responsible for UX/UI design. They create user-friendly interfaces and ensure a seamless user experience across all platforms.",
    member_count: 2,
    banner_image_url: "https://www.bio.org/act-root/bio/assets/images/banner-default.png",
    owners: [
      { id: "u3", username: "Charlie Brown", first_name: "Charlie", last_name: "Brown" },
      { id: "u4", username: "Diana Prince", first_name: "Diana", last_name: "Prince" },
    ],
  },
];
const { data: frontendConfig } = useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery();

export function TeamDetailsPage() {
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  // todo: get team from backend
  const team = teams[teamId];

  const tabs: TabConfig[] = [
    {
      label: frontendConfig.frontend_settings.properties.agentsNicknamePlural,
      path: `/team/${team.id}/${frontendConfig.frontend_settings.properties.agentsNicknamePlural}`,
      component: (
        <Box>
          <Typography>Lumis content for {team.name}</Typography>
        </Box>
      ),
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
      component: (
        <Box>
          <Typography>Apps content for {team.name}</Typography>
        </Box>
      ),
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
    <Box sx={{ px: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", height: "3rem" }}>
        <Typography variant="h6">{team.name}</Typography>
      </Box>
      <NavigationTabs tabs={tabs} />
    </Box>
  );
}
