import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { TeamCard } from "../components/teams/TeamCard";
import { useListTeamsKnowledgeFlowV1TeamsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export function TeamsPage() {
  const { t } = useTranslation();
  const { data: teams } = useListTeamsKnowledgeFlowV1TeamsGetQuery();

  const yourTeams = teams && teams.filter((t) => t.is_member);
  const otherTeams = teams && teams.filter((t) => !t.is_member);

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
          {yourTeams && yourTeams.map((team) => <TeamCard key={team.id} team={team} userIsMember />)}
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
          {otherTeams && otherTeams.map((team) => <TeamCard key={team.id} team={team} />)}
        </Box>
      </Box>
    </Box>
  );
}
