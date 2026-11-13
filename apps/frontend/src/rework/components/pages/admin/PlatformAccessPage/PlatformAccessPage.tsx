// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useState } from "react";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import Switch from "@shared/atoms/Switch/Switch";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import FilterChips from "@shared/molecules/FilterChips/FilterChips";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { stripDiacritics } from "@rework/utils/stripDiacritics";
import { getConfig } from "../../../../../common/config";
import {
  usePlatformAccessStateQuery,
  usePlatformAccessUsersQuery,
  usePlatformAccessT0Query,
  usePlatformAccessTeamsQuery,
  useSetPlatformFilteringMutation,
  useGrantPlatformUsersMutation,
  useRevokePlatformUserMutation,
  useRevokePlatformUsersMutation,
  usePlatformAccessPendingEmailsQuery,
  usePlatformAccessOverlapCountsQuery,
  useAddPlatformPendingEmailMutation,
  useRemovePlatformPendingEmailsMutation,
  useImportPlatformT0Mutation,
  useSetPlatformTeamMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AdmissionSource, PlatformAccessUser } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import PlatformAccessActivationDialog from "./PlatformAccessActivationDialog";
import PlatformAccessAddUsersDialog from "./PlatformAccessAddUsersDialog";
import PlatformAccessT0RefreshDialog from "./PlatformAccessT0RefreshDialog";
import PlatformAccessRuleEditor from "./PlatformAccessRuleEditor";
import styles from "./PlatformAccessPage.module.css";

const tabs = ["rules", "users", "teams"] as const;
// Searches on this page ignore accents and case, like the server-side user search.
const foldForSearch = (text: string) => stripDiacritics(text).toLocaleLowerCase();
const isIndividual = (source: AdmissionSource) => source.kind === "manual" || source.kind === "t0";
const individualSource = (user: PlatformAccessUser) => user.sources.find(isIndividual);
// One line per kind of access other than the individual one; teams of a kind share a line.
function otherAccessLines(user: PlatformAccessUser, t: TFunction): string[] {
  const kinds = new Set(user.sources.map((source) => source.kind));
  const teams = (kind: AdmissionSource["kind"]) =>
    user.sources
      .filter((source) => source.kind === kind)
      // A team without a name is never shown by its identifier.
      .map((source) => source.team_name || t("rework.platformAccess.otherAccess.unnamedTeam"));
  return [
    ...(kinds.has("attribute") ? [t("rework.platformAccess.otherAccess.attribute")] : []),
    ...(kinds.has("admin") ? [t("rework.platformAccess.otherAccess.admin")] : []),
    ...(["team", "free"] as const)
      .filter((kind) => kinds.has(kind))
      .map((kind) =>
        t(`rework.platformAccess.otherAccess.${kind}`, { count: teams(kind).length, teams: teams(kind).join(", ") }),
      ),
  ];
}
type Overlap = "rule" | "whitelist_only" | "unknown";
// "pending" lists whitelisted emails nobody signed in with yet, instead of people.
type View = Overlap | "pending";
// An empty filter is good news for cleanup: the icon says so rather than "nothing found".
const EMPTY_OVERLAP_ICON = {
  rule: "check_circle",
  whitelist_only: "shield",
  unknown: "check",
  pending: "check",
} as const;
// Header "select all" covers every matching row across pages: kept as the excluded rows, not a list.
type Selection = { mode: "ids"; ids: ReadonlySet<string> } | { mode: "all"; excluded: ReadonlySet<string> };
const NO_SELECTION: Selection = { mode: "ids", ids: new Set<string>() };
const ALL: Selection = { mode: "all", excluded: new Set<string>() };
const isSelected = (selection: Selection, id: string) =>
  selection.mode === "all" ? !selection.excluded.has(id) : selection.ids.has(id);
// A table reports its checked keys: fold each row's new state back into the selection.
function foldSelection(current: Selection, keys: ReadonlySet<string | number>, rowKeys: string[]): Selection {
  const toggled = new Set<string>(current.mode === "all" ? current.excluded : current.ids);
  rowKeys
    .filter((key) => keys.has(key) !== isSelected(current, key))
    .forEach((key) => (toggled.has(key) ? toggled.delete(key) : toggled.add(key)));
  return current.mode === "all" ? { mode: "all", excluded: toggled } : { mode: "ids", ids: toggled };
}
// First option of the table's rows-per-page selector.
const DEFAULT_PAGE_SIZE = 20;

export default function PlatformAccessPage() {
  const { t, i18n } = useTranslation();
  const { showError, showSuccess } = useToast();
  const enabled = getConfig()?.platform_access_enabled ?? false;
  const [tabIndex, setTabIndex] = useState(0);
  const panelId = useId();
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [query, setQuery] = useState("");
  const [teamQuery, setTeamQuery] = useState("");
  const [teamFilter, setTeamFilter] = useState<"allowed" | null>(null);
  const [overlap, setOverlap] = useState<View | null>(null);
  const [selection, setSelection] = useState<Selection>(NO_SELECTION);
  const [confirmingRemoval, setConfirmingRemoval] = useState(false);
  const [adding, setAdding] = useState(false);
  const [refreshingT0, setRefreshingT0] = useState(false);
  const [confirmingImport, setConfirmingImport] = useState(false);
  const [busy, setBusy] = useState(false);
  const [filterConfirmation, setFilterConfirmation] = useState<boolean>();
  const state = usePlatformAccessStateQuery(undefined, { skip: !enabled });
  const [searchQuery, setSearchQuery] = useState("");
  // Typing narrows a server-paginated list: wait for a pause, then restart at page one.
  useEffect(() => {
    const next = query.trim();
    if (next === searchQuery) return;
    const timer = setTimeout(() => {
      setSearchQuery(next);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [query, searchQuery]);
  const usersShown = enabled && tabIndex === 1;
  // The whitelist is the people holding an individual exception, never every known user.
  const users = usePlatformAccessUsersQuery(
    {
      offset,
      limit: pageSize,
      query: searchQuery,
      exceptionsOnly: true,
      ...(overlap && overlap !== "pending" ? { overlap } : {}),
    },
    { skip: !usersShown || overlap === "pending" },
  );
  // A selection is relative to one search and filter: changing either starts over.
  useEffect(() => setSelection(NO_SELECTION), [searchQuery, overlap]);
  const pendingEmails = usePlatformAccessPendingEmailsQuery(undefined, { skip: !usersShown });
  // One request per search, not per page: each chip shows how many people it lists.
  const overlapCounts = usePlatformAccessOverlapCountsQuery({ query: searchQuery }, { skip: !usersShown });
  const countOf = (key: Overlap) => overlapCounts.currentData?.[key];
  // Few enough to arrive in one response: the search narrows them here, like the teams.
  const pendingView = overlap === "pending";
  const pendingNeedle = foldForSearch(searchQuery);
  const pendingRows = (pendingEmails.data ?? []).filter((entry) => foldForSearch(entry.email).includes(pendingNeedle));
  // Rows of another page or search are never shown; the total keeps the pagination in place meanwhile.
  const userRows = users.isError ? undefined : users.currentData?.items;
  const userTotal = users.isError ? 0 : (users.currentData?.total ?? users.data?.total ?? 0);
  // A removal that empties the last page needs nothing here: the table snaps the offset back to the last page.
  // Each tab requests only what it shows: the import preview with Users, the teams listing with Teams.
  const t0 = usePlatformAccessT0Query({}, { skip: !usersShown });
  const teamsShown = enabled && tabIndex === 2;
  const teams = usePlatformAccessTeamsQuery(undefined, { skip: !teamsShown });
  // Teams arrive in one response, so the search only narrows what is already loaded.
  const teamNeedle = foldForSearch(teamQuery.trim());
  const teamRows = (teams.data ?? []).filter(
    (team) =>
      (teamFilter !== "allowed" || team.allowed) && foldForSearch(team.name || team.team_id).includes(teamNeedle),
  );
  const teamsNarrowed = teamNeedle !== "" || teamFilter !== null;
  const [filter] = useSetPlatformFilteringMutation();
  const [grantUsers] = useGrantPlatformUsersMutation();
  const [revoke] = useRevokePlatformUserMutation();
  const [revokeUsers] = useRevokePlatformUsersMutation();
  const [addPendingEmail] = useAddPlatformPendingEmailMutation();
  const [removePendingEmails] = useRemovePlatformPendingEmailsMutation();
  const viewTotal = pendingView ? pendingRows.length : userTotal;
  const selectedCount =
    selection.mode === "all" ? Math.max(viewTotal - selection.excluded.size, 0) : selection.ids.size;
  const everythingSelected = selection.mode === "all" && selection.excluded.size === 0;
  const [importT0] = useImportPlatformT0Mutation();
  const [setTeam] = useSetPlatformTeamMutation();
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      const detail = normalizeApiError(error).detail;
      showError({
        summary: t(
          detail === "platform_access_actor_lockout"
            ? "rework.platformAccess.actorLockout"
            : detail === "platform_access_policy_required"
              ? "rework.platformAccess.rule.required"
              : detail === "platform_access_email_known"
                ? "rework.platformAccess.addDialog.emailKnown"
                : "rework.platformAccess.failed",
        ),
      });
    } finally {
      setBusy(false);
    }
  };
  const locked = busy || state.isFetching || state.isError || !state.data;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.platformAccess.title")}
        subtitle={t("rework.platformAccess.description")}
        titleAction={
          enabled && state.data ? (
            <StatusBadge
              tone={state.data.filtering_enabled ? "success" : "neutral"}
              label={t(
                state.data.filtering_enabled
                  ? "rework.platformAccess.filteringOn"
                  : "rework.platformAccess.filteringOff",
              )}
            />
          ) : undefined
        }
        actions={
          enabled ? (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={locked || (!state.data?.filtering_enabled && !state.data?.has_admission_sources)}
              onClick={() => setFilterConfirmation(!state.data?.filtering_enabled)}
            >
              {t(
                state.data?.filtering_enabled
                  ? "rework.platformAccess.activation.disable"
                  : "rework.platformAccess.activation.enable",
              )}
            </Button>
          ) : undefined
        }
      />
      {!enabled ? (
        <p>{t("rework.platformAccess.disabled")}</p>
      ) : (
        <>
          {(state.isError ||
            (usersShown && users.isError) ||
            (teamsShown && teams.isError) ||
            (usersShown && t0.isError)) && <p role="alert">{t("rework.platformAccess.failed")}</p>}
          <div className={styles.navigation}>
            <ButtonGroup
              size="small"
              color="secondary"
              variant="tabs"
              aria-label={t("rework.platformAccess.tabs.label")}
              selectedIndex={tabIndex}
              onSelectedIndexChange={setTabIndex}
              items={tabs.map((tab) => ({
                id: `${panelId}-${tab}-tab`,
                "aria-controls": `${panelId}-${tab}-panel`,
                label: t(`rework.platformAccess.tabs.${tab}`),
              }))}
            />
          </div>
          <div
            className={styles.panel}
            id={`${panelId}-rules-panel`}
            role="tabpanel"
            aria-labelledby={`${panelId}-rules-tab`}
            hidden={tabIndex !== 0}
            tabIndex={0}
          >
            {state.data && (
              <PlatformAccessRuleEditor
                state={state.data}
                disabled={locked}
                reload={async () => (await state.refetch()).data}
              />
            )}
          </div>
          <div
            className={`${styles.panel} ${styles.fill}`}
            id={`${panelId}-users-panel`}
            role="tabpanel"
            aria-labelledby={`${panelId}-users-tab`}
            hidden={tabIndex !== 1}
            tabIndex={0}
          >
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>{t("rework.platformAccess.whitelistedUsers")}</h2>
              <p className={styles.hint} title={t("rework.platformAccess.whitelistedUsersHint")}>
                {t("rework.platformAccess.whitelistedUsersHint")}
              </p>
            </div>
            <div className={styles.toolbar}>
              <div className={styles.addActions}>
                <Button
                  color="primary"
                  variant="filled"
                  size="small"
                  icon={{ category: "outlined", type: "add" }}
                  disabled={locked}
                  onClick={() => setAdding(true)}
                >
                  {t("rework.platformAccess.addUsers")}
                </Button>
                <IconButtonMenu<"import" | "reimport">
                  iconButton={{
                    variant: "icon",
                    size: "medium",
                    color: "on-surface-retreat",
                    icon: { category: "outlined", type: "more_vert" },
                    "aria-label": t("rework.platformAccess.moreActions"),
                    disabled: locked || !t0.data || t0.isFetching || t0.isError,
                  }}
                  options={
                    t0.data?.completed_at
                      ? [
                          {
                            key: "reimport",
                            value: "reimport",
                            label: t("rework.platformAccess.t0Import"),
                          },
                        ]
                      : [
                          {
                            key: "import",
                            value: "import",
                            label: t("rework.platformAccess.t0Import"),
                          },
                        ]
                  }
                  onSelect={(action) => (action === "reimport" ? setRefreshingT0(true) : setConfirmingImport(true))}
                />
              </div>
              <div className={styles.toolbarGroup}>
                <FilterChips<View>
                  options={[
                    {
                      id: "rule",
                      label: t("rework.platformAccess.overlapFilter.rule"),
                      count: countOf("rule"),
                      tooltip: t("rework.platformAccess.overlapFilter.ruleHint"),
                    },
                    {
                      id: "whitelist_only",
                      label: t("rework.platformAccess.overlapFilter.whitelistOnly"),
                      count: countOf("whitelist_only"),
                      tooltip: t("rework.platformAccess.overlapFilter.whitelistOnlyHint"),
                    },
                    {
                      id: "unknown",
                      label: t("rework.platformAccess.overlapFilter.unknown"),
                      count: countOf("unknown"),
                      tooltip: t("rework.platformAccess.overlapFilter.unknownHint"),
                    },
                    {
                      id: "pending",
                      label: t("rework.platformAccess.overlapFilter.pending"),
                      count: pendingEmails.data ? pendingRows.length : undefined,
                      tooltip: t("rework.platformAccess.overlapFilter.pendingHint"),
                    },
                  ]}
                  value={overlap}
                  onChange={(next) => {
                    setOverlap(next);
                    setOffset(0);
                  }}
                  allLabel={t("rework.platformAccess.overlapFilter.all")}
                  allTooltip={t("rework.platformAccess.overlapFilter.allHint")}
                  aria-label={t("rework.platformAccess.overlapFilter.group")}
                />
                <div className={styles.search}>
                  <SearchInput
                    size="small"
                    value={query}
                    placeholder={t("rework.platformAccess.searchPlaceholder")}
                    ariaLabel={t("rework.platformAccess.search")}
                    clearAriaLabel={t("rework.platformAccess.clearSearch")}
                    onChange={setQuery}
                  />
                </div>
              </div>
            </div>
            {selectedCount > 0 && (
              <div
                className={styles.selectionBar}
                role="toolbar"
                aria-label={t("rework.platformAccess.selection.label")}
              >
                <span role="status">{t("rework.platformAccess.selection.count", { count: selectedCount })}</span>
                <Button
                  color="error"
                  variant="outlined"
                  size="small"
                  icon={{ category: "outlined", type: "delete" }}
                  disabled={locked || users.isFetching}
                  onClick={() => setConfirmingRemoval(true)}
                >
                  {t("rework.platformAccess.selection.remove")}
                </Button>
                <Button color="primary" variant="text" size="small" onClick={() => setSelection(NO_SELECTION)}>
                  {t("rework.platformAccess.selection.clear")}
                </Button>
              </div>
            )}
            {(pendingView ? pendingEmails.isFetching && !pendingEmails.data : users.isFetching && !userRows) && (
              <Spinner statusText={t("rework.platformAccess.loading")} />
            )}
            {usersShown &&
              (pendingView
                ? pendingEmails.data !== undefined && pendingRows.length === 0
                : !users.isFetching && !users.isError && userTotal === 0) && (
                <PageEmptyState
                  {...(searchQuery
                    ? {
                        icon: "search_off",
                        message: t("rework.platformAccess.noUsers"),
                        description: t("rework.platformAccess.emptyState.searchHint"),
                      }
                    : overlap
                      ? {
                          icon: EMPTY_OVERLAP_ICON[overlap],
                          message: t(`rework.platformAccess.emptyState.${overlap}.title`),
                          description: t(`rework.platformAccess.emptyState.${overlap}.hint`),
                        }
                      : {
                          icon: "person_add",
                          message: t("rework.platformAccess.emptyWhitelist"),
                          description: t("rework.platformAccess.emptyState.emptyHint"),
                          action: {
                            label: t("rework.platformAccess.addUsers"),
                            onClick: () => setAdding(true),
                            disabled: locked,
                          },
                        })}
                />
              )}
            {pendingView && pendingRows.length > 0 && (
              <DataTable
                size="small"
                data={pendingRows}
                rowKey={(entry) => entry.email}
                pageSize={DEFAULT_PAGE_SIZE}
                selectable
                selectedKeys={new Set(pendingRows.filter((e) => isSelected(selection, e.email)).map((e) => e.email))}
                onSelectionChange={(keys) =>
                  setSelection((current) =>
                    foldSelection(
                      current,
                      keys,
                      pendingRows.map((e) => e.email),
                    ),
                  )
                }
                headerSelection={{
                  checked: everythingSelected,
                  indeterminate: selectedCount > 0 && !everythingSelected,
                  onChange: () => setSelection(everythingSelected ? NO_SELECTION : ALL),
                  ariaLabel: t("rework.platformAccess.selection.selectAll"),
                }}
                columns={[
                  {
                    label: t("rework.platformAccess.pendingEmails.email"),
                    size: "1fr",
                    cellRenderer: (entry) => entry.email,
                  },
                  {
                    label: t("rework.platformAccess.addedOn"),
                    size: "11rem",
                    cellRenderer: (entry) => new Date(entry.granted_at).toLocaleString(i18n.language),
                  },
                  {
                    label: t("rework.platformAccess.exception"),
                    size: "10rem",
                    cellRenderer: (entry) => (
                      <Button
                        color="error"
                        variant="outlined"
                        size="small"
                        disabled={locked || pendingEmails.isFetching}
                        onClick={() =>
                          void run(async () => {
                            await removePendingEmails({
                              removePlatformAccessPendingEmails: { emails: [entry.email] },
                            }).unwrap();
                            showSuccess({
                              summary: t("rework.platformAccess.pendingEmails.removed", { email: entry.email }),
                            });
                          })
                        }
                      >
                        {t("rework.platformAccess.remove")}
                      </Button>
                    ),
                  },
                ]}
              />
            )}
            {!pendingView && userTotal > 0 && (
              <DataTable
                size="small"
                data={userRows ?? []}
                rowKey={(user) => user.user_id}
                selectable
                selectedKeys={
                  new Set(
                    (userRows ?? []).filter((user) => isSelected(selection, user.user_id)).map((user) => user.user_id),
                  )
                }
                onSelectionChange={(keys) =>
                  setSelection((current) =>
                    foldSelection(
                      current,
                      keys,
                      (userRows ?? []).map((user) => user.user_id),
                    ),
                  )
                }
                headerSelection={{
                  checked: everythingSelected,
                  indeterminate: selectedCount > 0 && !everythingSelected,
                  onChange: () => setSelection(everythingSelected ? NO_SELECTION : ALL),
                  ariaLabel: t("rework.platformAccess.selection.selectAll"),
                }}
                serverPagination={{
                  offset,
                  limit: pageSize,
                  totalCount: userTotal,
                  onOffsetChange: setOffset,
                  onLimitChange: (limit) => {
                    setPageSize(limit);
                    setOffset(0);
                  },
                }}
                columns={[
                  {
                    label: t("rework.teamSettings.members.table.identifiant"),
                    size: "1fr",
                    cellRenderer: (user) => user.username || user.email || "-",
                  },
                  {
                    label: t("rework.teamSettings.members.table.firstName"),
                    size: "1fr",
                    cellRenderer: (user) => user.first_name || "-",
                  },
                  {
                    label: t("rework.teamSettings.members.table.lastName"),
                    size: "1fr",
                    cellRenderer: (user) => user.last_name || "-",
                  },
                  {
                    label: t("rework.platformAccess.addedOn"),
                    size: "11rem",
                    cellRenderer: (user) => {
                      const grantedAt = individualSource(user)?.granted_at;
                      return grantedAt ? new Date(grantedAt).toLocaleString(i18n.language) : "-";
                    },
                  },
                  {
                    label: t("rework.platformAccess.origin.label"),
                    size: "8rem",
                    cellRenderer: (user) => {
                      const kind = individualSource(user)?.kind;
                      return kind ? t(`rework.platformAccess.origin.${kind}`) : "-";
                    },
                  },
                  {
                    // Empty means the individual access is the person's only one: removing it shuts them out.
                    label: t("rework.platformAccess.otherAccess.label"),
                    size: "9rem",
                    cellRenderer: (user) => {
                      const lines = otherAccessLines(user, t);
                      if (!lines.length) return null;
                      return (
                        <Tooltip
                          content={
                            <span className={styles.otherAccessPanel}>
                              {lines.map((line) => (
                                <span key={line}>{line}</span>
                              ))}
                            </span>
                          }
                        >
                          {/* Chip takes neither focus nor ARIA: this wrapper gives keyboard and screen-reader access. */}
                          <span
                            className={styles.otherAccess}
                            role="note"
                            tabIndex={0}
                            aria-label={t("rework.platformAccess.otherAccess.summary", {
                              details: lines.join(t("rework.platformAccess.otherAccess.separator")),
                            })}
                          >
                            <Chip label={t("rework.platformAccess.otherAccess.label")} title="" />
                          </span>
                        </Tooltip>
                      );
                    },
                  },
                  {
                    label: t("rework.platformAccess.exception"),
                    size: "10rem",
                    cellRenderer: (user) => (
                      <Button
                        color="error"
                        variant="outlined"
                        size="small"
                        disabled={locked || users.isFetching}
                        onClick={() =>
                          void run(async () => {
                            await revoke({ userId: user.user_id }).unwrap();
                            showSuccess({
                              summary: t("rework.platformAccess.revokedUser", {
                                user: user.username || user.email || user.user_id,
                              }),
                            });
                          })
                        }
                      >
                        {t("rework.platformAccess.remove")}
                      </Button>
                    ),
                  },
                ]}
              />
            )}
          </div>
          <div
            className={`${styles.panel} ${styles.fill}`}
            id={`${panelId}-teams-panel`}
            role="tabpanel"
            aria-labelledby={`${panelId}-teams-tab`}
            hidden={tabIndex !== 2}
            tabIndex={0}
          >
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>{t("rework.platformAccess.whitelistedTeams")}</h2>
              <p className={styles.hint} title={t("rework.platformAccess.whitelistedTeamsHint")}>
                {t("rework.platformAccess.whitelistedTeamsHint")}
              </p>
            </div>
            <div className={styles.toolbar}>
              <div className={styles.toolbarGroup}>
                <FilterChips<"allowed">
                  options={[
                    {
                      id: "allowed",
                      label: t("rework.platformAccess.teamFilter.allowed"),
                      count: (teams.data ?? []).filter((team) => team.allowed).length,
                    },
                  ]}
                  value={teamFilter}
                  onChange={setTeamFilter}
                  allLabel={t("rework.platformAccess.teamFilter.all")}
                  aria-label={t("rework.platformAccess.teamFilter.group")}
                />
                <div className={styles.search}>
                  <SearchInput
                    size="small"
                    value={teamQuery}
                    placeholder={t("rework.platformAccess.searchPlaceholder")}
                    ariaLabel={t("rework.platformAccess.searchTeam")}
                    clearAriaLabel={t("rework.platformAccess.clearSearch")}
                    onChange={setTeamQuery}
                  />
                </div>
              </div>
            </div>
            {teamsNarrowed && teamRows.length === 0 && (
              <p className={styles.hint}>{t("rework.platformAccess.noTeams")}</p>
            )}
            {(!teamsNarrowed || teamRows.length > 0) && (
              <DataTable
                size="small"
                data={teamRows}
                rowKey={(team) => team.team_id}
                pageSize={20}
                columns={[
                  {
                    label: t("rework.platformAccess.team"),
                    size: "2fr",
                    cellRenderer: (team) => team.name || team.team_id,
                    sortable: true,
                    sortValue: (team) => team.name || team.team_id,
                  },
                  {
                    label: t("rework.platformAccess.teamAllowed"),
                    size: "8rem",
                    cellRenderer: (team) => (
                      <Switch
                        size="small"
                        aria-label={`${t("rework.platformAccess.allowTeam")} ${team.name || team.team_id}`}
                        disabled={locked || teams.isFetching}
                        checked={team.allowed}
                        onChange={(event) =>
                          void run(() =>
                            setTeam({
                              teamId: team.team_id,
                              setPlatformAccessTeam: { allowed: event.target.checked, free: team.free },
                            }).unwrap(),
                          )
                        }
                      />
                    ),
                  },
                ]}
              />
            )}
          </div>
          <PlatformAccessAddUsersDialog
            open={adding}
            busy={busy}
            onClose={() => setAdding(false)}
            onConfirm={(userIds, emails) =>
              void run(async () => {
                if (userIds.length) await grantUsers({ grantPlatformAccessUsers: { user_ids: userIds } }).unwrap();
                for (const email of emails) {
                  await addPendingEmail({ addPlatformAccessPendingEmail: { email } }).unwrap();
                }
                showSuccess({
                  summary: t("rework.platformAccess.grantedSelected", { count: userIds.length + emails.length }),
                });
                setAdding(false);
                // Newest first: the people just added head the first page of the unfiltered list.
                setQuery("");
                setSearchQuery("");
                setOffset(0);
              })
            }
          />
          {refreshingT0 && <PlatformAccessT0RefreshDialog onClose={() => setRefreshingT0(false)} />}
          <ConfirmationDialog
            open={confirmingImport}
            title={t("rework.platformAccess.t0Confirm.title")}
            message={
              t0.data
                ? t("rework.platformAccess.t0Confirm.message", {
                    count: t0.data.candidates,
                    matching: t0.data.matching,
                  })
                : undefined
            }
            confirmLabel={t("rework.platformAccess.t0Confirm.confirm")}
            cancelLabel={t("common.cancel")}
            confirmDisabled={busy || !t0.data}
            onCancel={() => setConfirmingImport(false)}
            onConfirm={() =>
              void run(async () => {
                await importT0({ body: null }).unwrap();
                setConfirmingImport(false);
              })
            }
          />
          <ConfirmationDialog
            open={confirmingRemoval}
            criticalAction
            title={t("rework.platformAccess.bulkRemove.title", { count: selectedCount })}
            message={t("rework.platformAccess.bulkRemove.message")}
            confirmLabel={t("rework.platformAccess.bulkRemove.confirm")}
            cancelLabel={t("common.cancel")}
            confirmDisabled={busy}
            onCancel={() => setConfirmingRemoval(false)}
            onConfirm={() =>
              void run(async () => {
                const result = pendingView
                  ? await removePendingEmails({
                      removePlatformAccessPendingEmails: {
                        emails:
                          selection.mode === "all"
                            ? pendingRows.map((e) => e.email).filter((email) => !selection.excluded.has(email))
                            : [...selection.ids],
                      },
                    }).unwrap()
                  : await revokeUsers({
                      revokePlatformAccessUsers:
                        selection.mode === "all"
                          ? {
                              all_matching: true,
                              query: searchQuery,
                              overlap,
                              excluded_ids: [...selection.excluded],
                            }
                          : { user_ids: [...selection.ids] },
                    }).unwrap();
                showSuccess({ summary: t("rework.platformAccess.bulkRemove.done", { count: result.removed_count }) });
                setSelection(NO_SELECTION);
                setConfirmingRemoval(false);
              })
            }
          />
          {filterConfirmation !== undefined && state.data && (
            <PlatformAccessActivationDialog
              enabling={filterConfirmation}
              revision={state.data.revision}
              configured={state.data.has_admission_sources}
              busy={busy}
              onClose={() => setFilterConfirmation(undefined)}
              onImportUsers={() => {
                setFilterConfirmation(undefined);
                setTabIndex(1);
              }}
              onConfirm={(revision) =>
                void run(async () => {
                  await filter({
                    setPlatformFiltering: { filtering_enabled: filterConfirmation, expected_revision: revision },
                  }).unwrap();
                  setFilterConfirmation(undefined);
                })
              }
            />
          )}
        </>
      )}
    </div>
  );
}
