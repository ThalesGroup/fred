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
import FilterChips from "@shared/molecules/FilterChips/FilterChips";
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
  useImportPlatformT0Mutation,
  useSetPlatformTeamMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AdmissionSource, PlatformAccessUser } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import PlatformAccessActivationDialog from "./PlatformAccessActivationDialog";
import PlatformAccessAddUsersDialog from "./PlatformAccessAddUsersDialog";
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
  const [adding, setAdding] = useState(false);
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
    { offset, limit: pageSize, query: searchQuery, exceptionsOnly: true },
    { skip: !usersShown },
  );
  // Rows of another page or search are never shown; the total keeps the pagination in place meanwhile.
  const userRows = users.isError ? undefined : users.currentData?.items;
  const userTotal = users.isError ? 0 : (users.currentData?.total ?? users.data?.total ?? 0);
  // A removal that empties the last page needs nothing here: the table snaps the offset back to the last page.
  // Each tab requests only what it shows: the import preview with Users, the teams listing with Teams.
  const t0 = usePlatformAccessT0Query(undefined, { skip: !usersShown });
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
            className={styles.panel}
            id={`${panelId}-users-panel`}
            role="tabpanel"
            aria-labelledby={`${panelId}-users-tab`}
            hidden={tabIndex !== 1}
            tabIndex={0}
          >
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>{t("rework.platformAccess.whitelistedUsers")}</h2>
              <p className={styles.hint}>{t("rework.platformAccess.whitelistedUsersHint")}</p>
            </div>
            <div className={styles.toolbar}>
              <div className={styles.search}>
                <SearchInput
                  size="small"
                  value={query}
                  placeholder={t("rework.platformAccess.search")}
                  ariaLabel={t("rework.platformAccess.search")}
                  clearAriaLabel={t("rework.platformAccess.clearSearch")}
                  onChange={setQuery}
                />
              </div>
              <div className={styles.importRow}>
                {t0.data?.completed_at ? (
                  <span role="status">{t("rework.platformAccess.t0Done")}</span>
                ) : (
                  <>
                    {t0.data && (
                      <span>
                        {t("rework.platformAccess.t0Preview", {
                          count: t0.data.candidates,
                          matching: t0.data.matching,
                        })}
                      </span>
                    )}
                    <Button
                      color="primary"
                      variant="outlined"
                      size="small"
                      title={t("rework.platformAccess.t0Hint")}
                      disabled={locked || !t0.data || t0.isFetching || t0.isError}
                      onClick={() => void run(() => importT0().unwrap())}
                    >
                      {t("rework.platformAccess.t0Import")}
                    </Button>
                  </>
                )}
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
              </div>
            </div>
            {users.isFetching && !userRows && <Spinner statusText={t("rework.platformAccess.loading")} />}
            {usersShown && !users.isFetching && !users.isError && userTotal === 0 && (
              <p className={styles.hint}>
                {t(searchQuery ? "rework.platformAccess.noUsers" : "rework.platformAccess.emptyWhitelist")}
              </p>
            )}
            {userTotal > 0 && (
              <DataTable
                size="small"
                data={userRows ?? []}
                rowKey={(user) => user.user_id}
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
            className={styles.panel}
            id={`${panelId}-teams-panel`}
            role="tabpanel"
            aria-labelledby={`${panelId}-teams-tab`}
            hidden={tabIndex !== 2}
            tabIndex={0}
          >
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>{t("rework.platformAccess.whitelistedTeams")}</h2>
              <p className={styles.hint}>{t("rework.platformAccess.whitelistedTeamsHint")}</p>
            </div>
            <div className={styles.toolbar}>
              <div className={styles.search}>
                <SearchInput
                  size="small"
                  value={teamQuery}
                  placeholder={t("rework.platformAccess.searchTeam")}
                  ariaLabel={t("rework.platformAccess.searchTeam")}
                  clearAriaLabel={t("rework.platformAccess.clearSearch")}
                  onChange={setTeamQuery}
                />
              </div>
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
            onConfirm={(userIds) =>
              void run(async () => {
                await grantUsers({ grantPlatformAccessUsers: { user_ids: userIds } }).unwrap();
                showSuccess({ summary: t("rework.platformAccess.grantedSelected", { count: userIds.length }) });
                setAdding(false);
                // Newest first: the people just added head the first page of the unfiltered list.
                setQuery("");
                setSearchQuery("");
                setOffset(0);
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
