// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from "react";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
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
  const { showError } = useToast();
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
  const users = usePlatformAccessUsersQuery({ offset, limit: 25, query }, { skip: !enabled });
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
          {(state.isError || users.isError || teams.isError || t0.isError) && (
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
            <section className={styles.section}>
              <h2>{t("rework.platformAccess.users")}</h2>
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
                {t0.data?.completed_at ? (
                  <p className={styles.importCompleted} role="status">
                    {t("rework.platformAccess.t0Done")}
                  </p>
                ) : (
                  <section className={styles.section}>
                    <h2>{t("rework.platformAccess.t0Import")}</h2>
                    <p>{t("rework.platformAccess.t0Hint")}</p>
                    {t0.data && (
                      <p>
                        {t("rework.platformAccess.t0Preview", {
                          count: t0.data.candidates,
                          matching: t0.data.matching,
                        })}
                      </p>
                    )}
                    <Button
                      color="primary"
                      variant="filled"
                      size="medium"
                      disabled={locked || !t0.data || t0.isFetching || t0.isError}
                      onClick={() => void run(() => importT0().unwrap())}
                    >
                      {t("rework.platformAccess.t0Import")}
                    </Button>
                  </section>
                )}
                <section className={styles.section}>
                  <TextInput
                    label={t("rework.platformAccess.search")}
                    value={query}
                    onChange={(event) => {
                      setQuery(event.target.value);
                      setOffset(0);
                    }}
                  />
                  <p>{t("rework.platformAccess.bulkHint")}</p>
                  <div className={styles.row}>
                    <Button
                      color="primary"
                      variant="filled"
                      size="medium"
                      disabled={locked || selected.length === 0}
                      onClick={() =>
                        void run(async () => {
                          await grantUsers({ grantPlatformAccessUsers: { user_ids: selected } }).unwrap();
                          setSelected([]);
                        })
                      }
                    >
                      {t("rework.platformAccess.allowSelected", { count: selected.length })}
                    </Button>
                    <Button
                      color="primary"
                      variant="outlined"
                      size="medium"
                      disabled={locked || selected.length === 0}
                      onClick={() => setSelected([])}
                    >
                      {t("rework.platformAccess.clearSelection")}
                    </Button>
                  </div>
                  <DataTable
                    data={users.data?.items ?? []}
                    rowKey={(user) => user.user_id}
                    serverPagination={{
                      offset,
                      limit: 25,
                      totalCount: users.data?.total ?? 0,
                      onOffsetChange: setOffset,
                    }}
                    columns={[
                      {
                        label: t("rework.platformAccess.select"),
                        size: "0.5fr",
                        cellRenderer: (user) => (
                          <Checkbox
                            aria-label={t("rework.platformAccess.selectUser", { user: user.username || user.user_id })}
                            checked={selected.includes(user.user_id)}
                            disabled={locked || users.isFetching}
                            onChange={(event) => {
                              const checked = event.target.checked;
                              setSelected((current) =>
                                checked
                                  ? current.includes(user.user_id)
                                    ? current
                                    : [...current, user.user_id]
                                  : current.filter((id) => id !== user.user_id),
                              );
                            }}
                          />
                        ),
                      },
                      {
                        label: t("rework.teamSettings.members.table.identifiant"),
                        size: "2fr",
                        cellRenderer: (user) => (
                          <span>
                            {user.username || user.user_id}
                            <br />
                            {user.email}
                          </span>
                        ),
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
                        cellRenderer: (user) =>
                          user.sources.map((source, index) => (
                            <div key={index}>
                              {t(`rework.platformAccess.source.${source.kind}`)}
                              {source.team_id ? `: ${source.team_name || source.team_id} (${source.team_id})` : ""}
                            </div>
                          )),
                      },
                      {
                        label: t("rework.platformAccess.exception"),
                        size: "1.5fr",
                        cellRenderer: (user) => {
                          const hasIndividual = user.sources.some(
                            (source) => source.kind === "manual" || source.kind === "t0",
                          );
                          return (
                            <Button
                              color="primary"
                              variant="filled"
                              size="medium"
                              disabled={locked || users.isFetching}
                              onClick={() =>
                                void run(() => (hasIndividual ? revoke : grant)({ userId: user.user_id }).unwrap())
                              }
                            >
                              {t(hasIndividual ? "rework.platformAccess.remove" : "rework.platformAccess.allow")}
                            </Button>
                          );
                        },
                      },
                    ]}
                  />
                </section>
              </div>
              <div
                className={styles.panel}
                id={`${panelId}-whitelist-teams-panel`}
                role="tabpanel"
                aria-labelledby={`${panelId}-whitelist-teams-tab`}
                hidden={whitelistTabIndex !== 1}
                tabIndex={0}
              >
                <section className={styles.section}>
                  <h2>{t("rework.platformAccess.teams")}</h2>
                  <p>{t("rework.platformAccess.teamHint")}</p>
                  <DataTable
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
                        label: t("rework.platformAccess.allowTeam"),
                        size: "1fr",
                        cellRenderer: (team) => (
                          <Switch
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
                </section>
              </div>
            </section>
          </div>
          {filterConfirmation !== undefined && state.data && (
            <PlatformAccessActivationDialog
              enabling={filterConfirmation}
              revision={state.data.revision}
              configured={state.data.has_admission_sources}
              busy={locked}
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
