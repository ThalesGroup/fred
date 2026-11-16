// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { Navigate, useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { KeyCloakService } from "../../../../security/KeycloakService";
import Button from "@shared/atoms/Button/Button";
import { RoleChips } from "@shared/molecules/TeamRoleChips/TeamRoleChips";
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
  useRemoveSpaceMemberMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Role, SpaceMember } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamSettingsPage.module.scss";
import TeamInviteLinkDialog from "@shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamInviteLinkDialog/TeamInviteLinkDialog";
import TeamSettingsParameters from "@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters";
import TeamActivity from "./TeamActivity";
import { SpaceOffers } from "./SpaceOffers";
import { SpaceModels } from "./SpaceModels";

const ROLES: Role[] = ["owner", "editor", "analyst", "member"];
const userLabel = ({ user }: SpaceMember) => {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return name ? `${name} (${user.username ?? user.id})` : (user.username ?? user.id);
};

/** Governance only: existing Weaver grants/revocations, never implicit content access. */
export default function TeamSettingsPage() {
  const { teamId, section } = useParams();
  if (!teamId) return null;
  if (section === "parameters") return <TeamSettingsParameters key={teamId} spaceId={teamId} />;
  if (section === "models") return <SpaceModels key={teamId} spaceId={teamId} />;

  if (section === "activity") return <TeamActivity key={teamId} spaceId={teamId} />;
  if (section === "offers") return <SpaceOffers key={teamId} spaceId={teamId} />;
  if (section !== "members") return <Navigate to={`/team/${teamId}/settings/members`} replace />;
  return <TeamMembers key={teamId} spaceId={teamId} />;
}

function TeamMembers({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const access = useSpaceAccess(spaceId, "manage");
  const read = useSpaceAccess(spaceId, "read");
  const canRead = access.allowed || read.allowed;
  const navigate = useNavigate();
  const self = KeyCloakService.GetUserId();
  const memberships = useMySpacesQuery();
  const space = memberships.currentData?.find((item) => item.id === spaceId);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [removingMember, setRemovingMember] = useState<{ id: string; name: string }>();
  const [remove, removal] = useRemoveSpaceMemberMutation();
  const [candidates, setCandidates] = useState(false);
  const listingCandidates = candidates && access.allowed;
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const after = cursors[cursors.length - 1];
  const roster = useSpaceMembersQuery(
    { id: spaceId, after, search: search || undefined },
    { skip: !canRead || listingCandidates, refetchOnMountOrArgChange: true },
  );
  const eligible = useSpaceMemberCandidatesQuery(
    { id: spaceId, after, search: search || undefined },
    { skip: !access.allowed || !candidates, refetchOnMountOrArgChange: true },
  );
  const query = listingCandidates ? eligible : roster;
  const [grant, granting] = useGrantMutation();
  const [revoke, revoking] = useRevokeMutation();
  const [error, setError] = useState<string>();
  const busy = granting.isLoading || revoking.isLoading || removal.isLoading;
  const page = canRead && !query.isFetching && !query.isError ? query.currentData : undefined;
  const changeRole = async (member: SpaceMember, role: Role, checked: boolean) => {
    if (!access.allowed || busy) return;
    setError(undefined);
    try {
      const args = { id: spaceId, user: member.user.id, role };
      await (checked ? grant(args) : revoke(args)).unwrap();
    } catch (failure) {
      reportError(failure);
    }
  };
  const reportError = (failure: unknown) => {
    const { status, detail } = normalizeApiError(failure);
    setError(
      detail === "remove dependent child roles first"
        ? "dependentProjects"
        : detail?.startsWith("a non-personal space must retain")
          ? "lastOwner"
          : status === 409
            ? "conflict"
            : status === 403
              ? "forbidden"
              : "failed",
    );
  };
  const confirmRemoval = async () => {
    if (!removingMember || busy || !canRead || (removingMember.id !== self && !access.allowed)) return;
    setError(undefined);
    try {
      await remove({ id: spaceId, user: removingMember.id }).unwrap();
      if (removingMember.id === self) navigate("/home", { replace: true });
    } catch (failure) {
      reportError(failure);
    } finally {
      setRemovingMember(undefined);
    }
  };
  return (
    <div className={styles.teamSettingsPage}>
      <PageHeader title={t("rework.spaceMembers.title", { name: space?.name ?? "" })} />
      <p>{t(access.offered || access.allowed ? "rework.spaceMembers.separation" : "rework.spaceMembers.readOnly")}</p>
      <ConfirmationDialog
        open={!!removingMember}
        criticalAction
        title={t(removingMember?.id === self ? "rework.teamSettings.leaveTeam.title" : "rework.spaceMembers.remove")}
        message={t(
          removingMember?.id === self ? "rework.spaceMembers.leaveConfirm" : "rework.spaceMembers.removeConfirm",
          { name: removingMember?.name },
        )}
        confirmLabel={t("rework.spaceMembers.remove")}
        cancelLabel={t("common.cancel")}
        confirmDisabled={busy || !canRead || (removingMember?.id !== self && !access.allowed)}
        dismissible={!busy}
        onConfirm={() => void confirmRemoval()}
        onCancel={() => {
          if (!busy) setRemovingMember(undefined);
        }}
      />
      {error && <p role="alert">{t(`rework.spaceMembers.${error}`)}</p>}
      {!canRead && (access.error || read.error) ? (
        <p role="alert">{t("rework.manager.unavailable")}</p>
      ) : !canRead && (!access.settled || !read.settled) ? (
        <p role="status">{t("common.loading")}</p>
      ) : !canRead ? (
        <p role="alert">{t("rework.spaceMembers.forbidden")}</p>
      ) : (
        <>
          <div className={styles.actions}>
            {access.allowed && space?.kind === "team" && (
              <Button color="primary" variant="outlined" size="small" onClick={() => setInviteOpen(true)}>
                {t("rework.teamSettings.members.inviteLink.title")}
              </Button>
            )}
            {inviteOpen && access.allowed && (
              <TeamInviteLinkDialog teamId={spaceId} onClose={() => setInviteOpen(false)} />
            )}
            {access.allowed && (
              <Button
                color="primary"
                variant="outlined"
                size="small"
                disabled={busy}
                onClick={() => {
                  setCandidates(!candidates);
                  setSearch("");
                  setSearchDraft("");
                  setCursors([undefined]);
                  setError(undefined);
                }}
              >
                {t(candidates ? "rework.spaceMembers.roster" : "rework.spaceMembers.candidates")}
              </Button>
            )}
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
          <form
            className={styles.actions}
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchDraft.trim());
              setCursors([undefined]);
            }}
          >
            <SearchInput
              value={searchDraft}
              onChange={setSearchDraft}
              placeholder={t("rework.teamSettings.members.search.placeholder")}
              ariaLabel={t("rework.teamSettings.members.search.ariaLabel")}
              clearAriaLabel={t("rework.teamSettings.members.search.clearAriaLabel")}
              size="small"
            />
            <Button color="primary" variant="outlined" size="small" type="submit" disabled={busy}>
              {t("rework.spaceMembers.search")}
            </Button>
            {space && self && (
              <Button
                type="button"
                color="error"
                variant="text"
                size="small"
                disabled={busy || !canRead}
                onClick={() => setRemovingMember({ id: self, name: space.name })}
              >
                {t("rework.teamSettings.navigation.leaveTeam")}
              </Button>
            )}
          </form>
          {search && <p>{t("rework.spaceMembers.searchPages")}</p>}
          {listingCandidates && <p>{t("rework.spaceMembers.eligibility")}</p>}
          {query.isError ? (
            <p role="alert">{t("rework.manager.unavailable")}</p>
          ) : !page ? (
            <p role="status">{t("common.loading")}</p>
          ) : (
            <DataTable
              data={page.items}
              rowKey={(member) => member.user.id}
              columns={[
                {
                  label: t("rework.teamSettings.members.table.identifiant"),
                  size: "minmax(10rem, 1.3fr)",
                  cellRenderer: (member) => member.user.username ?? member.user.id,
                },
                {
                  label: t("rework.teamSettings.members.table.firstName"),
                  size: "minmax(7rem, 1fr)",
                  cellRenderer: (member) => member.user.first_name ?? "",
                },
                {
                  label: t("rework.teamSettings.members.table.lastName"),
                  size: "minmax(7rem, 1fr)",
                  cellRenderer: (member) => member.user.last_name ?? "",
                },
                {
                  label: t("rework.manager.roleLabel"),
                  size: "minmax(12rem, 2fr)",
                  cellRenderer: (member) => (
                    <RoleChips
                      size="small"
                      options={ROLES.map((role) => ({
                        key: role,
                        label: t(`rework.manager.roles.${role}`),
                        held: member.roles.includes(role),
                        disabled: busy || !access.allowed,
                        ariaLabel: `${userLabel(member)}: ${t(`rework.manager.roles.${role}`)}`,
                        onToggle: () => void changeRole(member, role, !member.roles.includes(role)),
                      }))}
                    />
                  ),
                },
                ...(access.allowed && !listingCandidates
                  ? [
                      {
                        label: t("rework.spaceMembers.actions"),
                        size: "6rem",
                        cellRenderer: (member: SpaceMember) => (
                          <Button
                            color="error"
                            variant="text"
                            size="small"
                            disabled={busy}
                            onClick={() => setRemovingMember({ id: member.user.id, name: userLabel(member) })}
                          >
                            {t("rework.spaceMembers.remove")}
                          </Button>
                        ),
                      },
                    ]
                  : []),
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
