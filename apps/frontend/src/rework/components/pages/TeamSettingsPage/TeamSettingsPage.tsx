// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useMySpacesQuery,
  useSpaceMembersQuery,
  useSpaceMemberCandidatesQuery,
  useGrantMutation,
  useRevokeMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Role, SpaceMember } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamSettingsPage.module.scss";

const ROLES: Role[] = ["owner", "member", "editor", "analyst"];
const userLabel = ({ user }: SpaceMember) => {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return name ? `${name} (${user.username ?? user.id})` : (user.username ?? user.id);
};

/** Governance only: existing Weaver grants/revocations, never implicit content access. */
export default function TeamSettingsPage() {
  const { teamId, section } = useParams();
  if (!teamId) return null;
  if (section !== "members") return <Navigate to={`/team/${teamId}/settings/members`} replace />;
  return <TeamMembers key={teamId} spaceId={teamId} />;
}

function TeamMembers({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const access = useSpaceAccess(spaceId, "manage");
  const memberships = useMySpacesQuery();
  const space = memberships.currentData?.find((item) => item.id === spaceId);
  const [candidates, setCandidates] = useState(false);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const after = cursors[cursors.length - 1];
  const roster = useSpaceMembersQuery(
    { id: spaceId, after },
    { skip: !access.allowed || candidates, refetchOnMountOrArgChange: true },
  );
  const eligible = useSpaceMemberCandidatesQuery(
    { id: spaceId, after },
    { skip: !access.allowed || !candidates, refetchOnMountOrArgChange: true },
  );
  const query = candidates ? eligible : roster;
  const [grant, granting] = useGrantMutation();
  const [revoke, revoking] = useRevokeMutation();
  const [error, setError] = useState<string>();
  const busy = granting.isLoading || revoking.isLoading;
  const page = access.allowed && !query.isFetching && !query.isError ? query.currentData : undefined;
  const changeRole = async (member: SpaceMember, role: Role, checked: boolean) => {
    if (!access.allowed || busy) return;
    setError(undefined);
    try {
      const args = { id: spaceId, user: member.user.id, role };
      await (checked ? grant(args) : revoke(args)).unwrap();
    } catch (failure) {
      const { status } = normalizeApiError(failure);
      setError(status === 409 ? "conflict" : status === 403 ? "forbidden" : "failed");
    }
  };
  return (
    <div className={styles.teamSettingsPage}>
      <PageHeader title={t("rework.spaceMembers.title", { name: space?.name ?? "" })} />
      <p>{t("rework.spaceMembers.separation")}</p>
      {error && <p role="alert">{t(`rework.spaceMembers.${error}`)}</p>}
      {access.error ? (
        <p role="alert">{t("rework.manager.unavailable")}</p>
      ) : !access.settled ? (
        <p role="status">{t("common.loading")}</p>
      ) : !access.allowed ? (
        <p role="alert">{t("rework.spaceMembers.forbidden")}</p>
      ) : (
        <>
          <div className={styles.actions}>
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={busy}
              onClick={() => {
                setCandidates(!candidates);
                setCursors([undefined]);
                setError(undefined);
              }}
            >
              {t(candidates ? "rework.spaceMembers.roster" : "rework.spaceMembers.candidates")}
            </Button>
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={busy || query.isFetching}
              onClick={() => void query.refetch()}
            >
              {t("rework.spaceMembers.refresh")}
            </Button>
          </div>
          {candidates && <p>{t("rework.spaceMembers.eligibility")}</p>}
          {query.isError ? (
            <p role="alert">{t("rework.manager.unavailable")}</p>
          ) : !page ? (
            <p role="status">{t("common.loading")}</p>
          ) : (
            <DataTable
              data={page.items}
              columns={[
                { label: t("rework.spaceMembers.person"), cellRenderer: (member) => <span>{userLabel(member)}</span> },
                ...ROLES.map((role) => ({
                  label: t(`rework.manager.roles.${role}`),
                  cellRenderer: (member: SpaceMember) => (
                    <Checkbox
                      checked={member.roles.includes(role)}
                      disabled={busy || !access.allowed}
                      aria-label={`${userLabel(member)}: ${t(`rework.manager.roles.${role}`)}`}
                      onChange={(event) => void changeRole(member, role, event.target.checked)}
                    />
                  ),
                })),
              ]}
            />
          )}
          {page?.items.length === 0 && <p>{t("rework.spaceMembers.empty")}</p>}
          <div className={styles.actions}>
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={busy || !page || cursors.length < 2}
              onClick={() => setCursors((values) => values.slice(0, -1))}
            >
              {t("dataTable.pagination.prev")}
            </Button>
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={busy || !page?.next_cursor}
              onClick={() => {
                if (page?.next_cursor) setCursors((values) => [...values, page.next_cursor!]);
              }}
            >
              {t("dataTable.pagination.next")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
