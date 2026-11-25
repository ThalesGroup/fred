// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { RoleChips } from "@shared/molecules/TeamRoleChips/TeamRoleChips";
import {
  useSpaceMemberCandidatesQuery,
  useSpaceMembersQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Role, SpaceMember, UserSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./SpaceMemberPicker.module.scss";

export const SPACE_ROLES: Role[] = ["owner", "editor", "analyst", "member"];

export const memberLabel = (user: UserSummary) => {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return name ? `${name} (${user.username ?? user.id})` : (user.username ?? user.id);
};

export interface PendingMember {
  user: UserSummary;
  roles: Role[];
}

const CONTENT_ROLES: Role[] = ["member", "editor", "analyst"];
// Both list people of a space page by page with the same arguments; a picker keeps one source.
const MEMBER_SOURCES = { candidates: useSpaceMemberCandidatesQuery, roster: useSpaceMembersQuery };

/**
 * Searches people and lists the selection with the roles each receives.
 * `candidates` asks the server who may join the space; `roster` offers the space's
 * own content holders, as for a project created inside a team.
 */
export default function SpaceMemberPicker({
  spaceId,
  source,
  eligibility,
  roles = SPACE_ROLES,
  pending,
  onPendingChange,
  disabled,
}: {
  spaceId: string;
  /** Fixed for the picker's lifetime. */
  source: keyof typeof MEMBER_SOURCES;
  eligibility: string;
  roles?: Role[];
  pending: PendingMember[];
  onPendingChange: (pending: PendingMember[]) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const eligibilityId = useId();
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [after, setAfter] = useState<string>();

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
  const useMembers = MEMBER_SOURCES[source];
  const query = useMembers({ id: spaceId, after, search }, { skip: !searchable, refetchOnMountOrArgChange: true });
  const page = searchable && wanted === search && !query.isFetching && !query.isError ? query.currentData : undefined;
  // The server scans the eligible list in bounded slices: an empty slice with a cursor is not "no match".
  const nextEmptySlice = page && page.items.length === 0 ? page.next_cursor : null;
  useEffect(() => {
    if (nextEmptySlice) setAfter(nextEmptySlice);
  }, [nextEmptySlice]);

  const pendingIds = new Set(pending.map((item) => item.user.id));
  const options = (page?.items ?? [])
    .filter((member) => !pendingIds.has(member.user.id))
    .map((member: SpaceMember) => {
      // A candidate already holding roles is a member; a roster person needs a content role.
      const refused =
        source === "roster" ? !member.roles.some((role) => CONTENT_ROLES.includes(role)) : member.roles.length > 0;
      return {
        key: member.user.id,
        value: member.user,
        label: memberLabel(member.user),
        disabled: refused,
        description: refused
          ? t(
              source === "roster"
                ? "rework.spaceMembers.add.contentRoleRequired"
                : "rework.spaceMembers.add.alreadyMember",
            )
          : undefined,
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

  const toggleRole = (userId: string, role: Role) =>
    onPendingChange(
      pending.map((item) =>
        item.user.id !== userId
          ? item
          : {
              ...item,
              roles: item.roles.includes(role) ? item.roles.filter((r) => r !== role) : [...item.roles, role],
            },
      ),
    );

  return (
    <>
      <span id={eligibilityId} className={styles.eligibility}>
        {eligibility}
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
            query.isError && wanted === search
              ? "rework.spaceMembers.add.searchFailed"
              : page
                ? "rework.spaceMembers.add.noMatch"
                : "rework.spaceMembers.add.searching",
          )}
          onFieldValueChange={setTyped}
          options={options}
          onSelect={(user) =>
            pendingIds.has(user.id)
              ? undefined
              : onPendingChange([...pending, { user, roles: [roles.includes("member") ? "member" : roles[0]] }])
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
                    disabled,
                    ariaLabel: `${memberLabel(item.user)}: ${t(`rework.manager.roles.${role}`)}`,
                    onToggle: () => toggleRole(item.user.id, role),
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
                  disabled={disabled}
                  onClick={() => onPendingChange(pending.filter((other) => other.user.id !== item.user.id))}
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
    </>
  );
}
