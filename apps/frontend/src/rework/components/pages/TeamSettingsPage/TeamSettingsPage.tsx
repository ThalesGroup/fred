// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { Navigate, useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { KeyCloakService } from "../../../../security/KeycloakService";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import Icon from "@shared/atoms/Icon/Icon";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { RoleChips } from "@shared/molecules/TeamRoleChips/TeamRoleChips";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useConversationTraceAccess } from "@core/hooks/useConversationTraceAccess";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useMySpacesQuery,
  useSpaceMembersQuery,
  useGrantMutation,
  useRevokeMutation,
  useRemoveSpaceMemberMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Role, SpaceMember } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import AddSpaceMembersDialog from "./AddSpaceMembersDialog";
import { memberLabel, SPACE_ROLES } from "./SpaceMemberPicker";
import styles from "./TeamSettingsPage.module.scss";
import TeamInviteLinkDialog from "@shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamInviteLinkDialog/TeamInviteLinkDialog";
import TeamSettingsParameters from "@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters";
import TeamActivity from "./TeamActivity";
import { SpaceOffers } from "./SpaceOffers";
import { SpaceModels } from "./SpaceModels";

const userLabel = ({ user }: SpaceMember) => memberLabel(user);

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

export function OrganizationObserversPage() {
  const { organizationId } = useConversationTraceAccess();
  return <TeamMembers key={organizationId} spaceId={organizationId} observers />;
}

function TeamMembers({ spaceId, observers = false }: { spaceId: string; observers?: boolean }) {
  const { t } = useTranslation();
  const access = useSpaceAccess(spaceId, observers ? "administer_organization" : "manage");
  const read = useSpaceAccess(spaceId, observers ? "administer_organization" : "read");
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
  const [adding, setAdding] = useState(false);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const after = cursors[cursors.length - 1];
  const query = useSpaceMembersQuery(
    { id: spaceId, after, search: search || undefined },
    { skip: !canRead || space?.kind === "organization", refetchOnMountOrArgChange: true },
  );
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
  // The control plane manages members of teams and projects only, not of an organization yet.
  if (space?.kind === "organization")
    return (
      <div className={`${styles.teamSettingsPage} ${styles.membersPage}`} data-shell-scroll="none">
        <PageHeader title={t("rework.spaceMembers.title")} />
        <span className={styles.notice} role="status">
          {t("rework.spaceMembers.organizationUnavailable")}
        </span>
      </div>
    );
  return (
    <div className={`${styles.teamSettingsPage} ${styles.membersPage}`} data-shell-scroll="none">
      <PageHeader
        title={t(observers ? "rework.admin.conversationTraces.observers" : "rework.spaceMembers.title")}
        titleAction={
          <>
            {/* Not a button: a plain icon whose explanation shows on hover or focus. */}
            <Tooltip
              content={t(
                access.offered || access.allowed ? "rework.spaceMembers.separation" : "rework.spaceMembers.readOnly",
              )}
              asChild
            >
              <span className={styles.titleInfo} tabIndex={0}>
                <Icon category="outlined" type="info" />
              </span>
            </Tooltip>
            {canRead && (
              <IconButtonMenu<"refresh" | "leave">
                iconButton={{
                  variant: "icon",
                  size: "small",
                  icon: { category: "outlined", type: "more_vert" },
                  "aria-label": t("rework.teamSettings.members.moreActions"),
                }}
                options={[
                  {
                    key: "refresh",
                    value: "refresh",
                    label: t("rework.spaceMembers.refresh"),
                    icon: { category: "outlined", type: "refresh" },
                    disabled: busy || query.isFetching,
                  },
                  ...(!observers && space && self
                    ? [
                        {
                          key: "leave",
                          value: "leave" as const,
                          label: t("rework.teamSettings.navigation.leaveTeam"),
                          icon: { category: "outlined", type: "logout" } as const,
                          destructive: true,
                          disabled: busy,
                        },
                      ]
                    : []),
                ]}
                onSelect={(action) => {
                  if (action === "refresh") void query.refetch();
                  else if (space && self) setRemovingMember({ id: self, name: space.name });
                }}
              />
            )}
          </>
        }
        actions={
          canRead && (
            <>
              <form
                className={styles.membersSearch}
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
                  size="xs"
                />
              </form>
              {access.allowed && space?.kind === "team" && (
                <Button color="primary" variant="outlined" size="small" onClick={() => setInviteOpen(true)}>
                  {t("rework.teamSettings.members.inviteLink.title")}
                </Button>
              )}
              {access.allowed && (space?.kind === "team" || space?.kind === "project" || observers) && (
                <Button
                  color="primary"
                  variant="filled"
                  size="small"
                  disabled={busy}
                  onClick={() => {
                    setError(undefined);
                    setAdding(true);
                  }}
                >
                  {t("rework.teamSettings.members.addMembersDialog.buttonLabel")}
                </Button>
              )}
            </>
          )
        }
      />
      {inviteOpen && access.allowed && <TeamInviteLinkDialog teamId={spaceId} onClose={() => setInviteOpen(false)} />}
      {adding && access.allowed && space && (space.kind === "team" || space.kind === "project" || observers) && (
        <AddSpaceMembersDialog
          spaceId={spaceId}
          kind={observers ? "organization" : (space.kind as "team" | "project")}
          roles={observers ? ["organization_observer"] : undefined}
          onClose={() => setAdding(false)}
        />
      )}
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
          {search && <p>{t("rework.spaceMembers.searchPages")}</p>}
          {query.isError ? (
            <p role="alert">{t("rework.manager.unavailable")}</p>
          ) : !page ? (
            <p role="status">{t("common.loading")}</p>
          ) : (
            <div className={styles.membersTable}>
              <DataTable
                size="medium"
                data={page.items}
                rowKey={(member) => member.user.id}
                columns={[
                  {
                    label: t("rework.teamSettings.members.table.identifiant"),
                    size: "minmax(0, 1.3fr)",
                    cellRenderer: (member) => member.user.username ?? member.user.id,
                  },
                  {
                    label: t("rework.teamSettings.members.table.firstName"),
                    size: "minmax(0, 1fr)",
                    cellRenderer: (member) => member.user.first_name ?? "",
                  },
                  {
                    label: t("rework.teamSettings.members.table.lastName"),
                    size: "minmax(0, 1fr)",
                    cellRenderer: (member) => member.user.last_name ?? "",
                  },
                  {
                    label: t("rework.manager.roleLabel"),
                    size: "minmax(9rem, 2fr)",
                    cellRenderer: (member) => (
                      <RoleChips
                        size="small"
                        options={(observers ? (["organization_observer"] as Role[]) : SPACE_ROLES).map((role) => ({
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
                  ...(!observers && access.allowed
                    ? [
                        {
                          label: t("rework.spaceMembers.actions"),
                          size: "3rem",
                          cellRenderer: (member: SpaceMember) => (
                            <IconButton
                              color="error"
                              variant="icon"
                              icon={{ category: "outlined", type: "delete" }}
                              aria-label={`${t("rework.spaceMembers.remove")}: ${userLabel(member)}`}
                              title={t("rework.spaceMembers.remove")}
                              size="small"
                              disabled={busy}
                              onClick={() => setRemovingMember({ id: member.user.id, name: userLabel(member) })}
                            />
                          ),
                        },
                      ]
                    : []),
                ]}
              />
            </div>
          )}
          {page?.items.length === 0 && <p>{t("rework.spaceMembers.empty")}</p>}
          <div className={styles.membersPagination}>
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
