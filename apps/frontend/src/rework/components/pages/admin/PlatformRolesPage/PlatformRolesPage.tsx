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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { userDisplayName } from "../../../../core/utils/userDisplayName";
import {
  useGrantPlatformRoleMutation,
  useListUsersQuery,
  usePlatformRolesQuery,
  useRevokePlatformRoleMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  PlatformRoleHolder,
  PlatformRoleRelation,
  UserSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PlatformRolesPage.module.css";

const displayName = (user: UserSummary) => userDisplayName(user.id, user);

/** Search haystack from the fields that exist — never the literal "undefined". */
const userHaystack = (user: UserSummary) =>
  [user.first_name, user.last_name, user.username, user.email].filter(Boolean).join(" ").toLowerCase();

// PLATFORM-ADMIN-DELEGATION-RFC.md §3.7 (#2405): root-managed admins,
// delegated observers. The visibility rules below only mirror what the
// backend enforces — `platform_admin` grant/revoke is shown to the bootstrap
// root only (`caller_is_bootstrap_root`), and the root's own row never gets a
// revoke affordance. Display-only: every action is re-checked server-side.
export default function PlatformRolesPage() {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();

  const [selectedUser, setSelectedUser] = useState<UserSummary | null>(null);
  const [userQuery, setUserQuery] = useState("");
  const [relation, setRelation] = useState<PlatformRoleRelation>("platform_observer");

  const { data: platformRoles, isLoading: isLoadingRoles, isError: isRolesError } = usePlatformRolesQuery();
  const { data: allUsers } = useListUsersQuery();
  const [grantRole, { isLoading: isGranting }] = useGrantPlatformRoleMutation();
  const [revokeRole] = useRevokePlatformRoleMutation();

  const callerIsRoot = platformRoles?.caller_is_bootstrap_root ?? false;

  const canRevoke = (holder: PlatformRoleHolder, revoked: PlatformRoleRelation) => {
    if (revoked === "platform_observer") return true;
    return callerIsRoot && !holder.is_bootstrap_root;
  };

  const handleRevoke = async (holder: PlatformRoleHolder, revoked: PlatformRoleRelation) => {
    await runMutationAction({
      action: () => revokeRole({ userId: holder.user.id, relation: revoked }).unwrap(),
      onSuccess: () =>
        showSuccess({
          summary: t("rework.platformRoles.revoke.successSummary", {
            role: t(`rework.platformRoles.roles.${revoked}`),
            user: displayName(holder.user),
          }),
        }),
      onError: (error) =>
        notifyApiError(error, {
          summary: t("rework.platformRoles.revoke.errors.summary"),
          fallbackDetail: t("rework.platformRoles.revoke.errors.fallbackDetail"),
          forbiddenDetail: t("rework.platformRoles.revoke.errors.forbiddenDetail"),
        }),
    });
  };

  // No useMemo: DataTable is not memoized, so caching the (2-element) column
  // array buys nothing and would force stale-closure deps management.
  const columns: DataTableColumn<PlatformRoleHolder>[] = [
    {
      label: t("rework.platformRoles.holders.table.user"),
      size: "2fr",
      cellRenderer: (holder) => (
        <div className={styles.userCell}>
          <span>{displayName(holder.user)}</span>
          {holder.user.username && <span className={styles.username}>{holder.user.username}</span>}
          {holder.is_bootstrap_root && (
            <span className={styles.rootBadge}>{t("rework.platformRoles.holders.rootBadge")}</span>
          )}
        </div>
      ),
    },
    {
      label: t("rework.platformRoles.holders.table.roles"),
      size: "2fr",
      cellRenderer: (holder) => (
        <div className={styles.rolesCell}>
          {holder.relations.map((held) => (
            <Chip
              key={held}
              label={t(`rework.platformRoles.roles.${held}`)}
              onRemove={canRevoke(holder, held) ? () => handleRevoke(holder, held) : undefined}
              removeAriaLabel={t("rework.platformRoles.revoke.ariaLabel", {
                role: t(`rework.platformRoles.roles.${held}`),
                user: displayName(holder.user),
              })}
            />
          ))}
        </div>
      ),
    },
  ];

  const suggestions = useMemo(() => {
    if (!allUsers) return [];
    const query = userQuery.toLowerCase().trim();
    return allUsers
      .filter((user) => user.id !== selectedUser?.id)
      .filter((user) => !query || userHaystack(user).includes(query));
  }, [allUsers, userQuery, selectedUser]);

  const canSubmit = selectedUser !== null && !isGranting && (relation !== "platform_admin" || callerIsRoot);

  const handleGrant = async () => {
    if (!selectedUser || !canSubmit) return;
    await runMutationAction({
      action: () =>
        grantRole({
          userId: selectedUser.id,
          grantPlatformRoleRequest: { relation },
        }).unwrap(),
      onSuccess: () => {
        showSuccess({
          summary: t("rework.platformRoles.grant.successSummary", {
            role: t(`rework.platformRoles.roles.${relation}`),
            user: displayName(selectedUser),
          }),
        });
        setSelectedUser(null);
      },
      onError: (error) =>
        notifyApiError(error, {
          summary: t("rework.platformRoles.grant.errors.summary"),
          fallbackDetail: t("rework.platformRoles.grant.errors.fallbackDetail"),
          forbiddenDetail: t("rework.platformRoles.grant.errors.forbiddenDetail"),
          conflictDetail: t("rework.platformRoles.grant.errors.conflictDetail"),
        }),
    });
  };

  const relationOptions: PlatformRoleRelation[] = ["platform_observer", "platform_admin"];

  const rootHolder = platformRoles?.holders.find((holder) => holder.is_bootstrap_root);

  const holdersContent = () => {
    if (isLoadingRoles) return <p className={styles.emptyMessage}>{t("rework.platformRoles.holders.loading")}</p>;
    if (isRolesError) return <p className={styles.errorMessage}>{t("rework.platformRoles.holders.error")}</p>;
    if (platformRoles && platformRoles.holders.length > 0)
      return <DataTable columns={columns} data={platformRoles.holders} />;
    return <p className={styles.emptyMessage}>{t("rework.platformRoles.holders.empty")}</p>;
  };

  return (
    <div className={styles.platformRolesPage}>
      <PageHeader title={t("rework.platformRoles.title")} />
      {rootHolder && (
        <div className={styles.rootCard}>
          <span className={styles.rootCardBadge}>{t("rework.platformRoles.holders.rootBadge")}</span>
          <div className={styles.rootCardIdentity}>
            <span className={styles.rootCardName}>{displayName(rootHolder.user)}</span>
            {rootHolder.user.username && <span className={styles.rootCardUsername}>{rootHolder.user.username}</span>}
          </div>
          <p className={styles.rootCardHint}>{t("rework.platformRoles.rootCard.hint")}</p>
        </div>
      )}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("rework.platformRoles.holders.title")}</h2>
        {holdersContent()}
      </section>
      <Separator />
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("rework.platformRoles.grant.title")}</h2>
        <div className={styles.grantField}>
          <span className={styles.grantLabel}>{t("rework.platformRoles.grant.userLabel")} *</span>
          <Autocomplete<UserSummary>
            textInput={{
              placeholder: t("rework.platformRoles.grant.userPlaceholder"),
              icon: { category: "outlined", type: "search" },
            }}
            onFieldValueChange={(value) => {
              setUserQuery(value);
              // Typing a new search drops the previous pick so the submit can
              // never target a user the visible text no longer names. The ""
              // fired by Autocomplete on selection must not clear it.
              if (value) setSelectedUser(null);
            }}
            options={suggestions.map((user) => ({
              label: user.username ? `${displayName(user)} (${user.username})` : displayName(user),
              value: user,
              key: user.id,
            }))}
            onSelect={setSelectedUser}
          />
          {selectedUser && (
            <Chip
              label={displayName(selectedUser)}
              onRemove={() => setSelectedUser(null)}
              removeAriaLabel={t("rework.platformRoles.grant.clearSelection")}
            />
          )}
        </div>
        <div className={styles.grantField}>
          <span className={styles.grantLabel}>{t("rework.platformRoles.grant.roleLabel")} *</span>
          <div className={styles.relationChoices}>
            {relationOptions.map((option) => (
              <Button
                key={option}
                color="primary"
                variant={relation === option ? "filled" : "outlined"}
                size="small"
                // platform_admin appointments are root-only (RFC §3) — shown
                // disabled rather than hidden so the rule stays discoverable.
                disabled={option === "platform_admin" && !callerIsRoot}
                onClick={() => setRelation(option)}
              >
                {t(`rework.platformRoles.roles.${option}`)}
              </Button>
            ))}
          </div>
          {!callerIsRoot && <p className={styles.rootOnlyHint}>{t("rework.platformRoles.grant.rootOnlyHint")}</p>}
        </div>
        <div className={styles.actions}>
          <Button color="primary" variant="filled" size="medium" disabled={!canSubmit} onClick={handleGrant}>
            {t("rework.platformRoles.grant.submit")}
          </Button>
        </div>
      </section>
    </div>
  );
}
