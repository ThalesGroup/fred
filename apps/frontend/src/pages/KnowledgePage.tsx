import { Box } from "@mui/material";
import { useParams } from "react-router-dom";
import { TeamDocumentsLibrary } from "../components/teamDetails/TeamDocumentsLibrary";
import { useFrontendBootstrap } from "../hooks/useFrontendBootstrap";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApiEnhancements";
import KnowledgeHubPage from "../rework/components/pages/KnowledgeHubPage/KnowledgeHubPage.tsx";

/**
 * Route a team knowledge page to the personal hub or a collaborative-team view.
 *
 * Why this component exists:
 * - the frontend still needs one route-level decision point while bootstrap and
 *   team selection are converging onto control-plane-owned state
 *
 * How to use it:
 * - mount it on `/team/:teamId/*` routes
 *
 * Example:
 * - `<KnowledgePage />`
 */
export function KnowledgePage() {
  const { teamId } = useParams<{ teamId: string }>();
  const { activeTeam } = useFrontendBootstrap();
  const personalTeamId = activeTeam?.id ?? "personal";
  const isPersonalTeam = teamId === personalTeamId;
  const { data: fetchedTeam } = useGetTeamQuery({ teamId: teamId || "" }, { skip: !teamId || isPersonalTeam });
  const team = isPersonalTeam ? activeTeam : fetchedTeam;

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
      {teamId === personalTeamId ? (
        <KnowledgeHubPage />
      ) : (
        <TeamDocumentsLibrary teamId={teamId} canCreateTag={team?.permissions?.includes("can_update_resources")} />
      )}
    </Box>
  );
}
