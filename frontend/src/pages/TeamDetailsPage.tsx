import { Box } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { NavigationTabs, TabConfig } from "../components/NavigationTabs";
import { TeamAppsPage } from "../components/teamDetails/TeamAppsPage";
import { TeamDocumentsLibrary } from "../components/teamDetails/TeamDocumentsLibrary";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApi";
import { KnowledgeHub } from "./KnowledgeHub.tsx";
import { useGetUserDetailsControlPlaneV1UserGetQuery } from "../slices/controlPlane/controlPlaneOpenApi.ts";

export function TeamDetailsPage() {
  const { t } = useTranslation();

  const { teamId } = useParams<{ teamId: string }>();
  const { data: userDetails } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const { data: fetchedTeam, isLoading } = useGetTeamQuery(
    { teamId: teamId },
    { skip: !teamId || teamId === userDetails?.personalTeam.id },
  );
  const team = fetchedTeam ?? userDetails?.personalTeam;
  // todo: handle error (404)

  if (teamId === undefined) {
    // Should never happen
    return <>need a team id in the url</>;
  }

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
