import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { TeamAppsPage } from "../components/teamDetails/TeamAppsPage";
import { TeamDocumentsLibrary } from "../components/teamDetails/TeamDocumentsLibrary";
import { TeamMembersPage } from "../components/teamDetails/TeamMembersPage";
import { TeamAvatar } from "../components/teams/TeamVisuals";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApi";
import { KnowledgeHub } from "./KnowledgeHub.tsx";

export function TeamDetailsPage() {
  const { t } = useTranslation();

  const { teamId } = useParams<{ teamId: string }>();
  const { data: team, isLoading } = useGetTeamQuery({ teamId: teamId !== "user" ? teamId : "" }, { skip: !teamId });
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

  const tabs: TabConfig[] = [
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
    ...(team?.permissions?.includes("can_read_members") ? [memberTab] : []),
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
        <TeamAvatar
          variant="rounded"
          teamName={team?.name}
          imageUrl={team?.banner_image_url}
          sx={{ height: "3.5rem", width: "3.5rem" }}
        />

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
        contentContainerSx={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", minHeight: 0 }}
        isLoading={isLoading}
      />
    </Box>
  );
}
