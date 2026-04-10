import { Box } from "@mui/material";
import { useParams } from "react-router-dom";
import { TeamDocumentsLibrary } from "../components/teamDetails/TeamDocumentsLibrary";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApiEnhancements";
import { useGetUserDetailsControlPlaneV1UserGetQuery } from "../slices/controlPlane/controlPlaneOpenApi.ts";
import { KnowledgeHub } from "./KnowledgeHub.tsx";

export function KnowledgePage() {
  const { teamId } = useParams<{ teamId: string }>();
  const { data: userDetails } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const isPersonalTeam = teamId === userDetails?.personalTeam.id;
  const { data: fetchedTeam } = useGetTeamQuery({ teamId: teamId || "" }, { skip: !teamId || isPersonalTeam });
  const team = isPersonalTeam ? fetchedTeam : userDetails?.personalTeam;

  // todo: handle error (404)

  if (teamId === undefined) {
    // Should never happen
    return <>need a team id in the url</>;
  }

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
      {teamId === userDetails?.personalTeam.id ? (
        <KnowledgeHub />
      ) : (
        <TeamDocumentsLibrary teamId={teamId} canCreateTag={team?.permissions?.includes("can_update_resources")} />
      )}
    </Box>
  );
}
