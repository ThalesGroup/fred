import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { TeamCard } from "../components/teams/TeamCard";
import { useListGroupsKnowledgeFlowV1GroupsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export function TeamsPage() {
  const { t } = useTranslation();
  const {
    data: groups = [],
    isLoading,
    isError,
  } = useListGroupsKnowledgeFlowV1GroupsGetQuery({
    limit: 10000,
    offset: 0,
    memberOnly: false,
  });

  const yourTeams = groups.filter((g) => g.is_member);
  const communityTeams = groups.filter((g) => !g.is_member);

  return (
    <Box sx={{ px: 2, pt: 1, pb: 2 }}>
      <Box sx={{ height: "3.5rem", display: "flex", alignItems: "center" }}>
        <Typography variant="h6" color="textSecondary">
          {t("teamsPage.title")}
        </Typography>
      </Box>

      {isLoading && (
        <Typography variant="body2" color="textSecondary">
          {t("common.loading")}
        </Typography>
      )}

      {isError && (
        <Typography variant="body2" color="error">
          {t("common.error")}
        </Typography>
      )}

      <Box sx={{ mb: 2 }}>
        {/* Your teams */}
        <Box sx={{ height: "2.5rem", display: "flex", alignItems: "center" }}>
          <Typography variant="subtitle1" color="textSecondary">
            {t("teamsPage.yourTeamsSubtitle")}
          </Typography>
        </Box>

        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {yourTeams.map((team) => (
            <TeamCard key={team.id} team={team} userIsMember />
          ))}
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
          {communityTeams.map((team) => (
            <TeamCard key={team.id} team={team} />
          ))}
        </Box>
      </Box>
    </Box>
  );
}
