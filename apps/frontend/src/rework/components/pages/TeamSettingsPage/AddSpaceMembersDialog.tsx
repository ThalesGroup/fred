// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { RoleChips } from "@shared/molecules/TeamRoleChips/TeamRoleChips";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useGrantMutation,
  useSpaceMemberCandidatesQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Role, SpaceMember, UserSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AddSpaceMembersDialog.module.scss";

export const SPACE_ROLES: Role[] = ["owner", "editor", "analyst", "member"];

export const memberLabel = (user: UserSummary) => {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return name ? `${name} (${user.username ?? user.id})` : (user.username ?? user.id);
};

interface Pending {
  user: UserSummary;
  roles: Role[];
}

/** Picks people the server lists as eligible and grants their roles in one explicit step. */
export default function AddSpaceMembersDialog({
  spaceId,
  kind,
  roles = SPACE_ROLES,
  onClose,
}: {
  spaceId: string;
  kind: "team" | "project" | "organization";
  /** The roles offered; an organization only adds observers here. */
  roles?: Role[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const eligibilityId = useId();
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [after, setAfter] = useState<string>();
  const [pending, setPending] = useState<Pending[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<"conflict" | "forbidden" | "failed">();
  const [grant] = useGrantMutation();

  // One request per pause in typing; a new search restarts from the first page.
  const wanted = typed.trim();
  useEffect(() => {
    if (wanted === search) return;
    const timer = setTimeout(() => {
      setSearch(wanted);
      setAfter(undefined);
    }, 300);
    return () => clearTimeout(timer);
  }, [wanted, search]);

  const searchable = search.length >= 2;
  const candidates = useSpaceMemberCandidatesQuery(
    { id: spaceId, after, search },
    { skip: !searchable, refetchOnMountOrArgChange: true },
  );
  const page =
    searchable && wanted === search && !candidates.isFetching && !candidates.isError
      ? candidates.currentData
      : undefined;
  // The server scans the eligible list in bounded slices: an empty slice with a cursor is not "no match".
  const nextEmptySlice = page && page.items.length === 0 ? page.next_cursor : null;
  useEffect(() => {
    if (nextEmptySlice) setAfter(nextEmptySlice);
  }, [nextEmptySlice]);

  const pendingIds = new Set(pending.map((item) => item.user.id));
  const options = (page?.items ?? [])
    .filter((member) => !pendingIds.has(member.user.id))
    .map((member: SpaceMember) => {
      const already = member.roles.length > 0;
      return {
        key: member.user.id,
        value: member.user,
        label: memberLabel(member.user),
        disabled: already,
        description: already ? t("rework.spaceMembers.add.alreadyMember") : undefined,
      };
    });
  const lastShown = page?.items[page.items.length - 1];
  if (page?.next_cursor && lastShown) {
    // A menu line, never selectable: it carries a user only because options are typed by their value.
    options.push({
      key: "more-matches",
      value: lastShown.user,
      label: t("rework.spaceMembers.add.more"),
      disabled: true,
      description: undefined,
    });
  }

  const setRoles = (userId: string, role: Role) =>
    setPending((items) =>
      items.map((item) =>
        item.user.id !== userId
          ? item
          : {
              ...item,
              roles: item.roles.includes(role) ? item.roles.filter((r) => r !== role) : [...item.roles, role],
            },
      ),
    );

  const confirm = async () => {
    if (submitting || pending.length === 0 || pending.some((item) => item.roles.length === 0)) return;
    setSubmitting(true);
    setError(undefined);
    let failure: unknown;
    const remaining: Pending[] = [];
    for (const item of pending) {
      const failed: Role[] = [];
      for (const role of item.roles) {
        try {
          await grant({ id: spaceId, user: item.user.id, role }).unwrap();
        } catch (caught) {
          failure ??= caught;
          failed.push(role);
        }
      }
      if (failed.length) remaining.push({ ...item, roles: failed });
    }
    setSubmitting(false);
    // Granting refreshes the roster through the SpaceMembers tag; only what failed stays selected.
    if (!remaining.length) return onClose();
    const { status } = normalizeApiError(failure);
    setPending(remaining);
    setError(status === 409 ? "conflict" : status === 403 ? "forbidden" : "failed");
  };

  return (
    <Dialog
      open
      maxWidth={640}
      title={t("rework.teamSettings.members.addMembersDialog.title")}
      confirmLabel={t("rework.teamSettings.members.addMembersDialog.confirm")}
      confirmDisabled={submitting || pending.length === 0 || pending.some((item) => item.roles.length === 0)}
      dismissible={!submitting}
      onConfirm={() => void confirm()}
      onCancel={() => {
        if (!submitting) onClose();
      }}
    >
      <div className={styles.body}>
        <span id={eligibilityId} className={styles.eligibility}>
          {t(`rework.spaceMembers.add.eligibility.${kind}`)}
        </span>
        <div className={styles.search}>
          <Autocomplete<UserSummary>
            textInput={{
              placeholder: t("rework.teamSettings.members.addMembersDialog.searchPlaceholder"),
              icon: { category: "outlined", type: "search" },
              "aria-label": t("rework.teamSettings.members.addMembersDialog.searchPlaceholder"),
              "aria-describedby": eligibilityId,
            }}
            minQueryLength={2}
            noOptionsMessage={t(
              candidates.isError && wanted === search
                ? "rework.spaceMembers.add.searchFailed"
                : page
                  ? "rework.spaceMembers.add.noMatch"
                  : "rework.spaceMembers.add.searching",
            )}
            onFieldValueChange={setTyped}
            options={options}
            onSelect={(user) =>
              setPending((items) =>
                items.some((item) => item.user.id === user.id)
                  ? items
                  : [...items, { user, roles: [roles.includes("member") ? "member" : roles[0]] }],
              )
            }
          />
        </div>
        <div className={styles.pendingContainer}>
          <span className={styles.pendingHeader}>{t("rework.spaceMembers.add.pendingListHeader")}</span>
          {pending.length > 0 ? (
            <ul className={styles.pendingList}>
              {pending.map((item) => (
                <li key={item.user.id} className={styles.pendingRow}>
                  <span className={styles.pendingName}>{memberLabel(item.user)}</span>
                  <RoleChips
                    size="small"
                    options={roles.map((role) => ({
                      key: role,
                      label: t(`rework.manager.roles.${role}`),
                      held: item.roles.includes(role),
                      disabled: submitting,
                      ariaLabel: `${memberLabel(item.user)}: ${t(`rework.manager.roles.${role}`)}`,
                      onToggle: () => setRoles(item.user.id, role),
                    }))}
                  />
                  <IconButton
                    variant="icon"
                    size="medium"
                    color="on-surface-retreat"
                    icon={{ category: "outlined", type: "close" }}
                    aria-label={t("rework.teamSettings.members.addMembersDialog.removeAria", {
                      name: memberLabel(item.user),
                    })}
                    disabled={submitting}
                    onClick={() => setPending((items) => items.filter((other) => other.user.id !== item.user.id))}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <span className={styles.pendingEmpty}>
              {t("rework.teamSettings.members.addMembersDialog.pendingListEmpty")}
            </span>
          )}
        </div>
        {pending.some((item) => item.roles.length === 0) && (
          <span className={styles.hint}>{t("rework.spaceMembers.add.roleRequired")}</span>
        )}
        {error && (
          <span role="alert" className={styles.error}>
            {t(`rework.spaceMembers.${error}`)}
          </span>
        )}
      </div>
    </Dialog>
  );
}
