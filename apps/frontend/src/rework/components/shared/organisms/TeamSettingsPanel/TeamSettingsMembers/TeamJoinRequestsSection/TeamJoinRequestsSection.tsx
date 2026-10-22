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

// Join requests waiting on this team's admins, plus the ones refused in the
// last 7 days ("Accept anyway", only while the team takes requests). The bell is
// the main surface; this list also covers an admin promoted after a request.

import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useAcceptTeamJoinRequestMutation,
  useRefuseTeamJoinRequestMutation,
  useTeamJoinRequestsQuery,
} from "../../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { TeamJoinRequest } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamJoinRequestsSection.module.scss";

interface TeamJoinRequestsSectionProps {
  teamId: string;
  canAdministerMembers: boolean;
  /** Public and `on_request`: otherwise a refused request can no longer be accepted. */
  takesRequests: boolean;
}

export default function TeamJoinRequestsSection({
  teamId,
  canAdministerMembers,
  takesRequests,
}: TeamJoinRequestsSectionProps) {
  const { t, i18n } = useTranslation();
  const { showError } = useToast();
  // Requesters and other admins act from their own sessions.
  const { data, refetch } = useTeamJoinRequestsQuery({ teamId }, crossSessionRefreshOptions(!canAdministerMembers));
  useRefetchOnWindowFocus(refetch, !canAdministerMembers);
  const requests = takesRequests ? data : data?.filter((request) => request.status === "pending");
  const [accept, { isLoading: accepting }] = useAcceptTeamJoinRequestMutation();
  const [refuse, { isLoading: refusing }] = useRefuseTeamJoinRequestMutation();
  const busy = accepting || refusing;

  if (!canAdministerMembers || !requests?.length) return null;

  // A failed decision (e.g. the request was cancelled meanwhile) refetches the list.
  const decide = (request: TeamJoinRequest, decision: "accept" | "refuse") => {
    const args = { teamId, requestId: request.id };
    (decision === "accept" ? accept(args) : refuse(args))
      .unwrap()
      .catch((error: unknown) =>
        showError({ summary: t("rework.notifications.actionFailed"), detail: normalizeApiError(error).detail }),
      );
  };

  const formatDate = (value: string) =>
    new Date(value).toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" });

  return (
    <section className={styles.section} aria-labelledby="team-join-requests-title">
      <h2 id="team-join-requests-title" className={styles.title}>
        {t("rework.teamSettings.members.joinRequests.title")}
      </h2>
      <ul className={styles.list}>
        {requests.map((request) => (
          <li key={request.id} className={styles.row}>
            <div className={styles.text}>
              <span className={styles.name}>{request.requester_name}</span>
              <span className={styles.meta}>
                {request.status === "refused" && request.decided_at
                  ? t("rework.teamSettings.members.joinRequests.refusedOn", { date: formatDate(request.decided_at) })
                  : t("rework.teamSettings.members.joinRequests.sentOn", { date: formatDate(request.created_at) })}
              </span>
              {request.message && <p className={styles.message}>{request.message}</p>}
            </div>
            <div className={styles.actions}>
              {request.status === "pending" ? (
                <>
                  <Button
                    color="error"
                    variant="outlined"
                    size="small"
                    disabled={busy}
                    onClick={() => decide(request, "refuse")}
                  >
                    {t("rework.teamSettings.members.joinRequests.refuse")}
                  </Button>
                  <Button
                    color="success"
                    variant="filled"
                    size="small"
                    disabled={busy}
                    onClick={() => decide(request, "accept")}
                  >
                    {t("rework.teamSettings.members.joinRequests.accept")}
                  </Button>
                </>
              ) : (
                <Button
                  color="success"
                  variant="outlined"
                  size="small"
                  disabled={busy}
                  onClick={() => decide(request, "accept")}
                >
                  {t("rework.teamSettings.members.joinRequests.acceptAnyway")}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
