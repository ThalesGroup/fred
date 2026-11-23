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
// last 7 days ("Accept anyway"). The bell is the main surface; this list also
// covers an admin promoted after a request. Rendered only for those admins.
import Button from "@shared/atoms/Button/Button.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
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
}

export default function TeamJoinRequestsSection({ teamId }: TeamJoinRequestsSectionProps) {
  const { t, i18n } = useTranslation();
  const { showError } = useToast();
  // Requesters and other admins act from their own sessions.
  const { data: requests, isError, refetch } = useTeamJoinRequestsQuery({ teamId }, crossSessionRefreshOptions(false));
  useRefetchOnWindowFocus(refetch, false);
  const [accept, { isLoading: accepting }] = useAcceptTeamJoinRequestMutation();
  const [refuse, { isLoading: refusing }] = useRefuseTeamJoinRequestMutation();
  const busy = accepting || refusing;

  // The same loading and error states as the bell's popover.
  if (!requests) {
    return isError ? (
      <p className={styles.status}>{t("rework.teamSettings.members.joinRequests.loadError")}</p>
    ) : (
      <div className={styles.status}>
        <Spinner />
      </div>
    );
  }
  if (requests.length === 0) {
    return <PageEmptyState icon="person_add" message={t("rework.teamSettings.members.joinRequests.empty")} />;
  }

  // A failed decision (e.g. the request was cancelled meanwhile) refetches the list.
  const decide = (request: TeamJoinRequest, decision: "accept" | "refuse") => {
    const args = { teamId, requestId: request.id };
    (decision === "accept" ? accept(args) : refuse(args))
      .unwrap()
      .catch((error: unknown) =>
        showError({ summary: t("rework.notifications.actionFailed"), detail: normalizeApiError(error).detail }),
      );
  };

  const formatDate = (value: string, dateStyle: "medium" | "full" = "medium") =>
    new Date(value).toLocaleString(i18n.language, { dateStyle, timeStyle: "short" });

  const meta = (request: TeamJoinRequest) => {
    const refusedAt = request.status === "refused" ? request.decided_at : null;
    const date = refusedAt ?? request.created_at;
    const label = refusedAt
      ? t("rework.teamSettings.members.joinRequests.refusedOn", { date: formatDate(date) })
      : t("rework.teamSettings.members.joinRequests.sentOn", { date: formatDate(date) });
    return (
      <time className={styles.meta} dateTime={date} title={formatDate(date, "full")}>
        {label}
      </time>
    );
  };

  return (
    <ul className={styles.list}>
      {requests.map((request) => (
        <li key={request.id} className={styles.row}>
          <div className={styles.text}>
            <div className={styles.heading}>
              <span className={styles.name} title={request.requester_name}>
                {request.requester_name}
              </span>
              {meta(request)}
            </div>
            {request.message && (
              <p className={styles.message} title={request.message}>
                {request.message}
              </p>
            )}
          </div>
          <div className={styles.actions}>
            {request.status === "pending" ? (
              <>
                <Button
                  color="error"
                  variant="filled"
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
  );
}
