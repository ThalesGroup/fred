// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import AddPeopleDialog from "@shared/organisms/AddPeopleDialog/AddPeopleDialog";
import type { PlatformAccessUser } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { usePlatformAccessUsersQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";

const PAGE_SIZE = 25;
// Mirrors the server's check; the server stays the authority.
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
// An email nobody signed in with travels as a pseudo user: one pending list for both.
const EMAIL_KEY = "email:";
const emailEntry = (email: string): PlatformAccessUser => ({
  user_id: `${EMAIL_KEY}${email}`,
  username: email,
  email,
  sources: [],
});

function userLabel(user: PlatformAccessUser): string {
  const identifier = user.username || user.email || user.user_id;
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return name ? `${name} (${identifier})` : identifier;
}

export default function PlatformAccessAddUsersDialog({
  open,
  busy,
  onClose,
  onConfirm,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onConfirm: (userIds: string[], emails: string[]) => void;
}) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [pending, setPending] = useState<PlatformAccessUser[]>([]);

  useEffect(() => {
    if (open) {
      setPending([]);
      setTyped("");
      setSearchQuery("");
    }
  }, [open]);

  // One request per pause in typing, not per keystroke: the search runs over every known user.
  const wanted = typed.trim();
  useEffect(() => {
    if (wanted === searchQuery) return;
    const timer = setTimeout(() => setSearchQuery(wanted), 300);
    return () => clearTimeout(timer);
  }, [wanted, searchQuery]);

  const searchable = open && searchQuery.length >= 2;
  const users = usePlatformAccessUsersQuery({ offset: 0, limit: PAGE_SIZE, query: searchQuery }, { skip: !searchable });
  const searchTooBroad = users.isError && normalizeApiError(users.error).detail === "platform_access_search_too_broad";
  // Only the answer to what is typed right now is offered, never an earlier search.
  const settled = searchable && wanted === searchQuery && !users.isFetching;
  const page = settled && !users.isError ? users.currentData : undefined;
  const pendingIds = new Set(pending.map((user) => user.user_id));
  const options: {
    key: string;
    value: PlatformAccessUser;
    label: string;
    disabled: boolean;
    description: string | undefined;
  }[] = (page?.items ?? [])
    .filter((user) => !pendingIds.has(user.user_id))
    .map((user) => {
      const granted = user.sources.some((source) => source.kind === "manual" || source.kind === "t0");
      return {
        key: user.user_id,
        value: user,
        label: userLabel(user),
        disabled: granted,
        description: granted ? t("rework.platformAccess.addDialog.alreadyGranted") : undefined,
      };
    });
  // Someone with no account yet is whitelisted by email, unless that address is already known.
  const typedEmail = wanted.toLowerCase();
  const offerEmail =
    page !== undefined &&
    EMAIL.test(typedEmail) &&
    !page.items.some((user) => user.email?.toLowerCase() === typedEmail) &&
    !pendingIds.has(`${EMAIL_KEY}${typedEmail}`);
  if (offerEmail) {
    options.unshift({
      key: `${EMAIL_KEY}${typedEmail}`,
      value: emailEntry(typedEmail),
      label: t("rework.platformAccess.addDialog.addEmail", { email: typedEmail }),
      disabled: false,
      description: t("rework.platformAccess.addDialog.emailDescription"),
    });
  }
  const lastShown = page?.items[page.items.length - 1];
  if (page && lastShown && page.total > page.items.length) {
    // A line of the menu, never selectable: it carries a user only because options are typed by their value.
    options.push({
      key: "more-matches",
      value: lastShown,
      label: t("rework.platformAccess.addDialog.more", { count: page.total - page.items.length }),
      disabled: true,
      description: undefined,
    });
  }

  return (
    <AddPeopleDialog<PlatformAccessUser>
      open={open}
      title={t("rework.platformAccess.addDialog.title")}
      subtitle={t("rework.platformAccess.addDialog.subtitle")}
      searchPlaceholder={t("rework.platformAccess.addDialog.searchPlaceholder")}
      noOptionsMessage={t(
        !settled
          ? "rework.platformAccess.addDialog.searching"
          : users.isError
            ? searchTooBroad
              ? "rework.platformAccess.addDialog.searchTooBroad"
              : "rework.platformAccess.addDialog.searchFailed"
            : "rework.platformAccess.addDialog.noMatch",
      )}
      options={options}
      onSearchChange={setTyped}
      onSelect={(user) =>
        setPending((current) => (current.some((item) => item.user_id === user.user_id) ? current : [...current, user]))
      }
      pending={pending}
      pendingKey={(user) => user.user_id}
      pendingLabel={userLabel}
      pendingListHeader={t("rework.platformAccess.addDialog.pendingListHeader")}
      pendingListEmpty={t("rework.platformAccess.addDialog.pendingListEmpty")}
      removeAriaLabel={(user) => t("rework.platformAccess.addDialog.removeAria", { name: userLabel(user) })}
      onRemove={(user) => setPending((current) => current.filter((item) => item.user_id !== user.user_id))}
      cancelLabel={t("common.cancel")}
      confirmLabel={t("rework.platformAccess.addDialog.confirm")}
      confirmDisabled={pending.length === 0 || busy}
      onConfirm={() => {
        const isEmail = (user: PlatformAccessUser) => user.user_id.startsWith(EMAIL_KEY);
        onConfirm(
          pending.filter((user) => !isEmail(user)).map((user) => user.user_id),
          pending.filter(isEmail).map((user) => user.email ?? ""),
        );
      }}
      // A grant in flight keeps the dialog, so a failure still shows the selection it was for.
      onClose={() => {
        if (!busy) onClose();
      }}
    />
  );
}
