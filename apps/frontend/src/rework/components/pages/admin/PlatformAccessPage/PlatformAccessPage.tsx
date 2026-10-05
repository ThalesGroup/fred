// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { getConfig } from "../../../../../common/config";
import { platformPath } from "../../../../../common/platformAccess";
import {
  usePlatformAccessStateQuery,
  usePlatformAccessUsersQuery,
  usePlatformAccessT0Query,
  usePlatformAccessTeamsQuery,
  useSetPlatformFilteringMutation,
  useGrantPlatformUserMutation,
  useRevokePlatformUserMutation,
  useImportPlatformT0Mutation,
  useSetPlatformTeamMutation,
  useGeneratePlatformLinkMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";

export default function PlatformAccessPage() {
  const { t } = useTranslation();
  const { showError } = useToast();
  const enabled = getConfig()?.platform_access_enabled ?? false;
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<string>();
  const state = usePlatformAccessStateQuery(undefined, { skip: !enabled });
  const users = usePlatformAccessUsersQuery({ offset, limit: 25, query }, { skip: !enabled });
  const t0 = usePlatformAccessT0Query(undefined, { skip: !enabled });
  const teams = usePlatformAccessTeamsQuery(undefined, { skip: !enabled });
  const [filter] = useSetPlatformFilteringMutation();
  const [grant] = useGrantPlatformUserMutation();
  const [revoke] = useRevokePlatformUserMutation();
  const [importT0] = useImportPlatformT0Mutation();
  const [setTeam] = useSetPlatformTeamMutation();
  const [generate] = useGeneratePlatformLinkMutation();
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
      <PageHeader title={t("rework.platformAccess.title")} subtitle={t("rework.platformAccess.description")} />
      {!enabled ? (
        <p>{t("rework.platformAccess.disabled")}</p>
      ) : (
        <>
          {(state.isError || users.isError || teams.isError || t0.isError) && (
            <p role="alert">{t("rework.platformAccess.failed")}</p>
          )}
          <section className={styles.section}>
            <label className={styles.row}>
              <Switch
                aria-label={t("rework.platformAccess.filter")}
                checked={state.data?.filtering_enabled ?? false}
                disabled={locked}
                onChange={(event) =>
                  void run(() => filter({ setPlatformFiltering: { filtering_enabled: event.target.checked } }).unwrap())
                }
              />
              {t("rework.platformAccess.filter")}
            </label>
            <p>{t("rework.platformAccess.t0Hint")}</p>
            {t0.data && (
              <p>{t("rework.platformAccess.t0Preview", { count: t0.data.candidates, matching: t0.data.matching })}</p>
            )}
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={locked || !t0.data || !!t0.data.completed_at}
              onClick={() => void run(() => importT0().unwrap())}
            >
              {t(t0.data?.completed_at ? "rework.platformAccess.t0Done" : "rework.platformAccess.t0Import")}
            </Button>
          </section>
          <section className={styles.section}>
            <h2>{t("rework.platformAccess.users")}</h2>
            <TextInput
              label={t("rework.platformAccess.search")}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOffset(0);
              }}
            />
            <DataTable
              data={users.data?.items ?? []}
              rowKey={(user) => user.user_id}
              serverPagination={{ offset, limit: 25, totalCount: users.data?.total ?? 0, onOffsetChange: setOffset }}
              columns={[
                {
                  label: t("rework.platformAccess.user"),
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
                  label: t("rework.platformAccess.sources"),
                  size: "3fr",
                  cellRenderer: (user) =>
                    user.sources.map((source, index) => (
                      <div key={index}>
                        {t(`rework.platformAccess.source.${source.kind}`)}
                        {source.team_name ? `: ${source.team_name}` : ""}
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
          <section className={styles.section}>
            <h2>{t("rework.platformAccess.teams")}</h2>
            <p>{t("rework.platformAccess.freeHint")}</p>
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
                {
                  label: t("rework.platformAccess.free"),
                  size: "1fr",
                  cellRenderer: (team) => (
                    <Switch
                      aria-label={`Free ${team.name || team.team_id}`}
                      disabled={locked || teams.isFetching}
                      checked={team.free}
                      onChange={(event) => {
                        setLink(undefined);
                        void run(() =>
                          setTeam({
                            teamId: team.team_id,
                            setPlatformAccessTeam: { allowed: team.allowed, free: event.target.checked },
                          }).unwrap(),
                        );
                      }}
                    />
                  ),
                },
                {
                  label: t("rework.platformAccess.link"),
                  size: "2fr",
                  cellRenderer: (team) => (
                    <Button
                      color="primary"
                      variant="filled"
                      size="medium"
                      disabled={locked || !team.free || teams.isFetching}
                      onClick={() =>
                        void run(async () => {
                          const result = await generate({ teamId: team.team_id }).unwrap();
                          setLink(
                            new URL(platformPath(`join-free/${result.token}`), window.location.origin).toString(),
                          );
                        })
                      }
                    >
                      {t(
                        team.has_enrollment_link
                          ? "rework.platformAccess.rotateLink"
                          : "rework.platformAccess.createLink",
                      )}
                    </Button>
                  ),
                },
              ]}
            />
            {link && (
              <TextInput
                label={t("rework.platformAccess.copyLink")}
                value={link}
                readOnly
                onFocus={(event) => event.target.select()}
              />
            )}
          </section>
        </>
      )}
    </div>
  );
}
