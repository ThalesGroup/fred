// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import Button from "@shared/atoms/Button/Button.tsx";
import { PageError } from "@components/pages/PageError/PageError.tsx";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import JoinRequestDialog from "@shared/organisms/TeamCard/JoinRequestDialog.tsx";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap.ts";
import type { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useGetTeamQuery,
  useMyTeamJoinRequestsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";

/** Keeps a non-member (e.g. one who left, following an old link) out of a team's pages. */
export default function TeamMemberGate({ children }: { children: ReactNode }) {
  const { teamId } = useParams<{ teamId: string }>();
  const { activeTeam } = useFrontendBootstrap();
  const skip = !teamId || isPersonalTeamId(teamId) || teamId === activeTeam?.id;
  // Fresh on every team change: a cached team could predate joining or leaving it.
  const {
    data: team,
    error,
    isFetching,
  } = useGetTeamQuery(
    { teamId: teamId ?? "" },
    {
      skip,
      refetchOnMountOrArgChange: true,
    },
  );

  if (skip) return <>{children}</>;
  const status = error ? normalizeApiError(error).status : undefined;
  const denied = status === 403 || status === 404;
  const outsider = !isFetching && team?.id === teamId && team.is_member === false;
  if (!denied && !outsider) return <>{children}</>;
  return <NotAMember team={denied ? undefined : team} />;
}

function NotAMember({ team }: { team?: Pick<Team, "id" | "name" | "visibility" | "joining_mode"> }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [askOpen, setAskOpen] = useState(false);
  const canAsk = !!team && team.visibility === "public" && team.joining_mode === "on_request";
  const { data: myRequests } = useMyTeamJoinRequestsQuery(undefined, { skip: !canAsk });
  const pending = myRequests?.some((r) => r.team_id === team?.id && r.status === "pending");

  return (
    <>
      <PageError
        title={t("rework.teamMemberGate.title")}
        message={pending ? t("rework.teamMemberGate.pending") : t("rework.teamMemberGate.message")}
        actions={
          canAsk && !pending ? (
            <Button color="primary" variant="filled" size="medium" onClick={() => setAskOpen(true)}>
              {t("rework.teamCard.askToJoin")}
            </Button>
          ) : (
            <Button color="primary" variant="outlined" size="medium" onClick={() => navigate("/marketplace/teams")}>
              {t("rework.teamMemberGate.browseTeams")}
            </Button>
          )
        }
      />
      {canAsk && <JoinRequestDialog team={team} open={askOpen} onClose={() => setAskOpen(false)} />}
    </>
  );
}
