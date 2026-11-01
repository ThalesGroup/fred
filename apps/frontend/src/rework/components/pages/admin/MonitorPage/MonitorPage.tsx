// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import Button from "@shared/atoms/Button/Button";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import { ExpandableInfoContainer } from "@shared/molecules/ExpandableInfoContainer/ExpandableInfoContainer";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { useMonitorStatusQuery } from "../../../../../slices/monitor/monitorOpenApi";
import { monitorVerdict } from "./monitorVerdict";
import styles from "./MonitorPage.module.css";

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
  const verdict = snapshot ? monitorVerdict(snapshot) : undefined;
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
      <p className={styles.secondary} role="status">
        {access.isLoading || access.isFetching || query.isFetching
          ? t("rework.monitor.refreshing")
          : !access.isError && snapshot && t("rework.monitor.observed", { time: time(snapshot.observed_at) })}
      </p>
      {access.isLoading || (access.isFetching && !access.currentData) ? null : access.isError ? (
        <ServiceNotice
          color="error"
          title={t("rework.provisioning.authorityUnavailable")}
          action={
            <Button color="primary" variant="outlined" size="medium" onClick={() => void access.refetch()}>
              {t("rework.provisioning.retryAuthority")}
            </Button>
          }
        />
      ) : !access.isAdmin ? (
        <ServiceNotice color="error" title={t("rework.monitor.forbidden")} />
      ) : query.isError && errorKey !== "unavailable" ? (
        <ServiceNotice color="error" title={t(`rework.monitor.${errorKey}`)} />
      ) : (
        <div aria-live="polite">
          {query.isError ? (
            <ExpandableInfoContainer color="warning" icon="help" title={t("rework.monitor.unreachable")}>
              {t("rework.monitor.unavailable")}
            </ExpandableInfoContainer>
          ) : verdict ? (
            <ExpandableInfoContainer
              color={verdict.level === "ok" ? "success" : verdict.level}
              icon={verdict.level === "ok" ? "check_circle" : verdict.level}
              title={t(`rework.monitor.verdict.${verdict.level}`, {
                count: verdict.level === "ok" ? verdict.ready.length : verdict.findings.length,
              })}
            >
              {verdict.level === "ok" ? (
                <div className={styles.details}>
                  {verdict.ready.join(" · ")}
                  {verdict.inactive > 0 && <p>{t("rework.monitor.inactive", { count: verdict.inactive })}</p>}
                </div>
              ) : (
                <ul className={styles.details}>
                  {verdict.findings.map((finding) => (
                    <li key={`${finding.service}/${finding.kind}`}>
                      <div className={styles.finding}>
                        <StatusBadge tone={finding.level} label={t(`rework.monitor.states.${finding.kind}`)} />
                        {finding.service && <strong>{finding.service}</strong>}
                        <span>
                          {t(`rework.monitor.findings.${finding.kind}`, {
                            ready: finding.ready,
                            desired: finding.desired,
                            time: finding.at ? time(finding.at) : "",
                            sources: finding.sources?.map((source) => t(`rework.monitor.sources.${source}`)).join(", "),
                          })}
                          {finding.reason && ` (${finding.reason})`}
                        </span>
                      </div>
                      {finding.event && <p className={styles.secondary}>&quot;{finding.event}&quot;</p>}
                    </li>
                  ))}
                </ul>
              )}
            </ExpandableInfoContainer>
          ) : null}
        </div>
      )}
    </div>
  );
}
