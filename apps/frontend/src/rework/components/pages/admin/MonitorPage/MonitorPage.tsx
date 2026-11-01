// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import Button from "@shared/atoms/Button/Button";
import StatusBadge, { type StatusBadgeTone } from "@shared/atoms/StatusBadge/StatusBadge";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import { useMonitorStatusQuery, type ServiceState } from "../../../../../slices/monitor/monitorOpenApi";
import styles from "./MonitorPage.module.css";

const tones: Record<ServiceState, StatusBadgeTone> = {
  ready: "success",
  degraded: "error",
  updating: "warning",
  inactive: "neutral",
  unknown: "neutral",
};

export default function MonitorPage() {
  const { t, i18n } = useTranslation();
  const access = useManagerPlatformAdmin();
  const query = useMonitorStatusQuery(undefined, {
    skip: !access.isAdmin,
    pollingInterval: 15_000,
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(query.refetch, !access.isAdmin);
  // Never retain protected data on a failed authorization or failed refresh.
  const snapshot = access.isAdmin && !query.isError ? query.currentData : undefined;
  const time = (value: string) => new Date(value).toLocaleString(i18n.resolvedLanguage);
  const errorStatus = query.error && "status" in query.error ? query.error.status : undefined;
  const errorKey = errorStatus === 403 ? "forbidden" : errorStatus === 503 ? "authorizationUnavailable" : "unavailable";

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.monitor.title")}
        subtitle={t("rework.monitor.description")}
        actions={
          access.isAdmin && (
            <Button
              color="primary"
              variant="outlined"
              size="medium"
              disabled={query.isFetching}
              onClick={() => void query.refetch()}
            >
              {t("rework.monitor.refresh")}
            </Button>
          )
        }
      />
      {access.isLoading || (access.isFetching && !access.currentData) ? (
        <p role="status">{t("common.loading")}</p>
      ) : access.isError ? (
        <div role="alert">
          <p>{t("rework.provisioning.authorityUnavailable")}</p>
          <Button color="primary" variant="outlined" size="medium" onClick={() => void access.refetch()}>
            {t("rework.provisioning.retryAuthority")}
          </Button>
        </div>
      ) : !access.isAdmin ? (
        <p role="alert">{t("rework.monitor.forbidden")}</p>
      ) : query.isError ? (
        <p role="alert">{t(`rework.monitor.${errorKey}`)}</p>
      ) : !snapshot ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <>
          <p className={styles.description} role="status">
            {t("rework.monitor.observed", { namespace: snapshot.namespace, time: time(snapshot.observed_at) })}
            {query.isFetching ? ` · ${t("rework.monitor.refreshing")}` : ` · ${t("rework.monitor.polling")}`}
          </p>
          {snapshot.unavailable_sources.length > 0 && (
            <p role="alert">
              {t("rework.monitor.partial", {
                sources: snapshot.unavailable_sources.map((s) => t(`rework.monitor.sources.${s}`)).join(", "),
              })}
            </p>
          )}
          {snapshot.truncated_sources.length > 0 && (
            <p role="alert">
              {t("rework.monitor.truncated", {
                sources: snapshot.truncated_sources.map((s) => t(`rework.monitor.sources.${s}`)).join(", "),
              })}
            </p>
          )}
          <section className={styles.section} aria-labelledby="monitor-services">
            <h2 id="monitor-services">{t("rework.monitor.services")}</h2>
            {snapshot.services.length === 0 ? (
              <p>
                {t(
                  snapshot.unavailable_sources.some((s) => ["deployments", "stateful_sets", "daemon_sets"].includes(s))
                    ? "rework.monitor.dataUnavailable"
                    : "rework.monitor.noServices",
                )}
              </p>
            ) : (
              <DataTable
                data={snapshot.services}
                rowKey={(row) => `${row.kind}/${row.name}`}
                pageSize={25}
                columns={[
                  {
                    label: t("rework.monitor.service"),
                    cellRenderer: (row) => <span title={row.name}>{row.name}</span>,
                  },
                  { label: t("rework.monitor.kind"), cellRenderer: (row) => <span>{row.kind}</span> },
                  {
                    label: t("rework.monitor.replicas"),
                    cellRenderer: (row) => (
                      <span>
                        {row.ready} / {row.desired}
                      </span>
                    ),
                  },
                  {
                    label: t("rework.monitor.state"),
                    cellRenderer: (row) => (
                      <StatusBadge tone={tones[row.state]} label={t(`rework.monitor.states.${row.state}`)} />
                    ),
                  },
                ]}
              />
            )}
          </section>
          <section className={styles.section} aria-labelledby="monitor-containers">
            <h2 id="monitor-containers">{t("rework.monitor.containers")}</h2>
            <p className={styles.description}>{t("rework.monitor.restartExplanation")}</p>
            {snapshot.containers.length === 0 ? (
              <p>
                {t(
                  snapshot.unavailable_sources.includes("pods")
                    ? "rework.monitor.dataUnavailable"
                    : "rework.monitor.noContainers",
                )}
              </p>
            ) : (
              <DataTable
                data={snapshot.containers}
                rowKey={(row) => `${row.pod}/${row.init}/${row.container}`}
                pageSize={25}
                columns={[
                  { label: t("rework.monitor.pod"), cellRenderer: (row) => <span title={row.pod}>{row.pod}</span> },
                  {
                    label: t("rework.monitor.container"),
                    cellRenderer: (row) => (
                      <span title={row.container}>
                        {row.container || "—"}
                        {row.init ? " (init)" : ""}
                      </span>
                    ),
                  },
                  { label: t("rework.monitor.restarts"), cellRenderer: (row) => <span>{row.restarts}</span> },
                  {
                    label: t("rework.monitor.state"),
                    cellRenderer: (row) => (
                      <span title={row.reason || row.phase}>
                        {row.reason || (row.ready ? t("rework.monitor.states.ready") : row.phase)}
                      </span>
                    ),
                  },
                  {
                    label: t("rework.monitor.lastExit"),
                    cellRenderer: (row) => {
                      const detail = [row.last_exit_reason, row.last_exit_at ? time(row.last_exit_at) : null]
                        .filter(Boolean)
                        .join(" · ");
                      return <span title={detail}>{detail || "—"}</span>;
                    },
                  },
                ]}
              />
            )}
          </section>
          <section className={styles.section} aria-labelledby="monitor-events">
            <h2 id="monitor-events">{t("rework.monitor.events")}</h2>
            <p className={styles.description}>
              {t("rework.monitor.eventExplanation", { minutes: snapshot.event_window_seconds / 60 })}
            </p>
            {snapshot.events_limited && <p>{t("rework.monitor.eventsLimited")}</p>}
            {snapshot.events.length === 0 ? (
              <p>
                {t(
                  snapshot.unavailable_sources.includes("events")
                    ? "rework.monitor.dataUnavailable"
                    : "rework.monitor.noEvents",
                )}
              </p>
            ) : (
              <ol className={styles.events}>
                {snapshot.events.map((event) => (
                  <li key={event.uid} className={styles.event}>
                    <div className={styles.eventHeader}>
                      <StatusBadge
                        tone={event.severity === "Warning" ? "warning" : "info"}
                        label={event.severity === "Warning" ? t("rework.monitor.warning") : t("rework.monitor.normal")}
                      />
                      <strong>{event.reason}</strong>
                      <time dateTime={event.observed_at}>{time(event.observed_at)}</time>
                      <span>{t("rework.monitor.occurrences", { count: event.count })}</span>
                    </div>
                    <p>{event.object}</p>
                    <p>{event.message}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  );
}
