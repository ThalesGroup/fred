import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { TeamCard } from "../components/teams/TeamCard";
import { GroupSummary } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

const teams: GroupSummary[] = [
  {
    id: "1",
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
    id: "2",
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
    id: "3",
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

export function TeamsPage() {
  const { t } = useTranslation();
  // const { data: teams } = useListGroupsKnowledgeFlowV1GroupsGetQuery();

  return (
    <Box sx={{ px: 2, pt: 1, pb: 2 }}>
      <Box sx={{ height: "3.5rem", display: "flex", alignItems: "center" }}>
        <Typography variant="h6" color="textSecondary">
          {t("teamsPage.title")}
        </Typography>
      </Box>

      <Box sx={{ mb: 2 }}>
        {/* Your teams */}
        <Box sx={{ height: "2.5rem", display: "flex", alignItems: "center" }}>
          <Typography variant="subtitle1" color="textSecondary">
            {t("teamsPage.yourTeamsSubtitle")}
          </Typography>
        </Box>

        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {teams && teams.map((team) => <TeamCard key={team.id} team={team} userIsMember />)}
        </Box>
      </Box>

      <Box>
        {/*  */}
        <Box sx={{ height: "2.5rem", display: "flex", alignItems: "center" }}>
          <Typography variant="subtitle1" color="textSecondary">
            {t("teamsPage.communityTeamsSubtitle")}
          </Typography>
        </Box>

        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {teams &&
            [...teams, ...teams, ...teams, ...teams, ...teams].map((team) => <TeamCard key={team.id} team={team} />)}
        </Box>
      </Box>
    </Box>
  );
}
