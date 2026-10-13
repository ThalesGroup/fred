// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useState } from "react";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import Switch from "@shared/atoms/Switch/Switch";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { getConfig } from "../../../../../common/config";
import {
  usePlatformAccessStateQuery,
  usePlatformAccessUsersQuery,
  usePlatformAccessT0Query,
  usePlatformAccessTeamsQuery,
  useSetPlatformFilteringMutation,
  useGrantPlatformUserMutation,
  useGrantPlatformUsersMutation,
  useRevokePlatformUserMutation,
  useImportPlatformT0Mutation,
  useSetPlatformTeamMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import PlatformAccessActivationDialog from "./PlatformAccessActivationDialog";
import PlatformAccessRuleEditor from "./PlatformAccessRuleEditor";
import styles from "./PlatformAccessPage.module.css";

const tabs = ["rules", "users"] as const;
const whitelistTabs = ["users", "teams"] as const;

export default function PlatformAccessPage() {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const enabled = getConfig()?.platform_access_enabled ?? false;
  const [tabIndex, setTabIndex] = useState(0);
  const [whitelistTabIndex, setWhitelistTabIndex] = useState(0);
  const panelId = useId();
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [filterConfirmation, setFilterConfirmation] = useState<boolean>();
  const state = usePlatformAccessStateQuery(undefined, { skip: !enabled });
  const [searchQuery, setSearchQuery] = useState("");
  // Typing narrows a server-paginated list of every known user: wait for a pause, then restart at page one.
  useEffect(() => {
    const next = query.trim();
    if (next === searchQuery) return;
    const timer = setTimeout(() => {
      setSearchQuery(next);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [query, searchQuery]);
  const usersShown = enabled && tabIndex === 1 && whitelistTabIndex === 0;
  const users = usePlatformAccessUsersQuery({ offset, limit: 25, query: searchQuery }, { skip: !usersShown });
  // Rows of another page or search are never shown; the total keeps the pagination in place meanwhile.
  const userRows = users.isError ? undefined : users.currentData?.items;
  const userTotal = users.isError ? 0 : (users.currentData?.total ?? users.data?.total ?? 0);
  const t0 = usePlatformAccessT0Query(undefined, { skip: !enabled });
  const teams = usePlatformAccessTeamsQuery(undefined, { skip: !enabled });
  const [filter] = useSetPlatformFilteringMutation();
  const [grant] = useGrantPlatformUserMutation();
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
          {(state.isError || (usersShown && users.isError) || teams.isError || t0.isError) && (
            <p role="alert">{t("rework.platformAccess.failed")}</p>
          )}
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
            <p className={styles.hint}>{t("rework.platformAccess.whitelistHint")}</p>
            <div className={styles.navigation}>
              <ButtonGroup
                size="small"
                color="secondary"
                variant="tabs"
                aria-label={t("rework.platformAccess.whitelistTabs.label")}
                selectedIndex={whitelistTabIndex}
                onSelectedIndexChange={setWhitelistTabIndex}
                items={whitelistTabs.map((tab) => ({
                  id: `${panelId}-whitelist-${tab}-tab`,
                  "aria-controls": `${panelId}-whitelist-${tab}-panel`,
                  label: t(`rework.platformAccess.whitelistTabs.${tab}`),
                }))}
              />
            </div>
            <div
              className={styles.panel}
              id={`${panelId}-whitelist-users-panel`}
              role="tabpanel"
              aria-labelledby={`${panelId}-whitelist-users-tab`}
              hidden={whitelistTabIndex !== 0}
              tabIndex={0}
            >
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
                {t0.data?.completed_at ? (
                  <p className={styles.importCompleted} role="status">
                    {t("rework.platformAccess.t0Done")}
                  </p>
                ) : (
                  <div className={styles.importRow}>
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
                  </div>
                )}
              </div>
              {selected.length > 0 && (
                <div className={styles.selectionBar}>
                  <span>{t("rework.platformAccess.selectedCount", { count: selected.length })}</span>
                  <Button
                    color="primary"
                    variant="outlined"
                    size="small"
                    disabled={locked}
                    onClick={() =>
                      void run(async () => {
                        await grantUsers({ grantPlatformAccessUsers: { user_ids: selected } }).unwrap();
                        showSuccess({
                          summary: t("rework.platformAccess.grantedSelected", { count: selected.length }),
                        });
                        setSelected([]);
                      })
                    }
                  >
                    {t("rework.platformAccess.allowSelected")}
                  </Button>
                  <IconButton
                    color="on-surface-retreat"
                    variant="icon"
                    size="small"
                    icon={{ category: "outlined", type: "close" }}
                    title={t("rework.platformAccess.clearSelection")}
                    aria-label={t("rework.platformAccess.clearSelection")}
                    disabled={locked}
                    onClick={() => setSelected([])}
                  />
                </div>
              )}
              {users.isFetching && !userRows && <Spinner statusText={t("rework.platformAccess.loading")} />}
              {usersShown && !users.isFetching && !users.isError && userTotal === 0 && (
                <p className={styles.hint}>
                  {t(searchQuery ? "rework.platformAccess.noUsers" : "rework.platformAccess.noKnownUsers")}
                </p>
              )}
              {userTotal > 0 && (
                <DataTable
                  size="small"
                  data={userRows ?? []}
                  rowKey={(user) => user.user_id}
                  selectable
                  selectedKeys={new Set(selected)}
                  // Selection stays frozen while a change is being saved, as the row checkboxes were.
                  onSelectionChange={(keys) => {
                    if (!locked) setSelected([...keys].map(String));
                  }}
                  serverPagination={{
                    offset,
                    limit: 25,
                    totalCount: userTotal,
                    onOffsetChange: setOffset,
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
                      label: t("rework.platformAccess.sources"),
                      size: "3fr",
                      cellRenderer: (user) => (
                        <div className={styles.accessSources}>
                          {user.sources.length
                            ? user.sources.map((source, index) => (
                                <Chip
                                  key={index}
                                  label={`${t(`rework.platformAccess.source.${source.kind}`)}${source.team_name ? `: ${source.team_name}` : ""}`}
                                />
                              ))
                            : "-"}
                        </div>
                      ),
                    },
                    {
                      label: t("rework.platformAccess.exception"),
                      size: "10rem",
                      cellRenderer: (user) => {
                        const hasIndividual = user.sources.some(
                          (source) => source.kind === "manual" || source.kind === "t0",
                        );
                        return (
                          <Button
                            color={hasIndividual ? "error" : "primary"}
                            variant="outlined"
                            size="small"
                            disabled={locked || users.isFetching}
                            onClick={() =>
                              void run(async () => {
                                await (hasIndividual ? revoke : grant)({ userId: user.user_id }).unwrap();
                                showSuccess({
                                  summary: t(
                                    hasIndividual
                                      ? "rework.platformAccess.revokedUser"
                                      : "rework.platformAccess.grantedUser",
                                    { user: user.username || user.email || user.user_id },
                                  ),
                                });
                              })
                            }
                          >
                            {t(hasIndividual ? "rework.platformAccess.remove" : "rework.platformAccess.allow")}
                          </Button>
                        );
                      },
                    },
                  ]}
                />
              )}
            </div>
            <div
              className={styles.panel}
              id={`${panelId}-whitelist-teams-panel`}
              role="tabpanel"
              aria-labelledby={`${panelId}-whitelist-teams-tab`}
              hidden={whitelistTabIndex !== 1}
              tabIndex={0}
            >
              <div className={styles.group}>
                <p className={styles.hint}>{t("rework.platformAccess.teamHint")}</p>
                <DataTable
                  size="small"
                  data={teams.data ?? []}
                  rowKey={(team) => team.team_id}
                  pageSize={20}
                  columns={[
                    {
                      label: t("rework.platformAccess.team"),
                      size: "2fr",
                      cellRenderer: (team) => team.name || team.team_id,
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
              </div>
            </div>
          </div>
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
                setWhitelistTabIndex(0);
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
