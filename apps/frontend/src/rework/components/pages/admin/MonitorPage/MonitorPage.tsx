// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
  const globalFindings = verdict?.findings.filter((finding) => !finding.service) ?? [];
  const components = [
    ...(snapshot?.services.map((service) => ({
      id: `${service.kind}/${service.name}`,
      name: service.name,
      service,
      findings: verdict?.findings.filter((finding) => finding.service === service.name) ?? [],
    })) ?? []),
    ...(globalFindings.length
      ? [{ id: "global", name: t("rework.monitor.global"), service: undefined, findings: globalFindings }]
      : []),
  ];
  const selected = components.find((component) => component.id === selectedId);
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
            <Button color="primary" variant="outlined" size="medium" onClick={() => void query.refetch()}>
              {t("rework.monitor.refresh")}
            </Button>
          )
        }
      />
      <p className={styles.secondary} role="status">
        {!access.isError && snapshot
          ? t("rework.monitor.observed", { time: time(snapshot.observed_at) })
          : (access.isFetching || query.isFetching) && t("rework.monitor.refreshing")}
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
            <div className={styles.overview}>
              <h2 className={styles.heading}>
                {t(`rework.monitor.verdict.${verdict.level}`, {
                  count: verdict.level === "ok" ? verdict.ready.length : verdict.findings.length,
                })}
              </h2>
              {components.length > 0 && <p className={styles.secondary}>{t("rework.monitor.selectComponent")}</p>}
              <div className={styles.chips} role="group" aria-label={t("rework.monitor.components")}>
                {components.map((component) => {
                  const finding = component.findings[0];
                  const state = finding?.kind ?? component.service?.state ?? "unknown";
                  const color = finding?.level ?? (state === "ready" ? "success" : "on-surface-retreat");
                  return (
                    <Button
                      key={component.id}
                      className={styles.chip}
                      color={color}
                      variant="tonal"
                      size="medium"
                      data-color={color}
                      aria-expanded={selected?.id === component.id}
                      aria-controls={selected?.id === component.id ? "monitor-component-detail" : undefined}
                      icon={{
                        category: "outlined",
                        type: color === "success" ? "check_circle" : (finding?.level ?? "remove"),
                      }}
                      onClick={() => setSelectedId(selectedId === component.id ? null : component.id)}
                      onKeyDown={(event) => event.key === "Escape" && setSelectedId(null)}
                    >
                      <span className={styles.label}>
                        <span className={styles.name} title={component.name}>
                          {component.name}
                        </span>
                        <span className={styles.state}>{t(`rework.monitor.states.${state}`)}</span>
                      </span>
                    </Button>
                  );
                })}
              </div>
              {selected && (
                <section
                  id="monitor-component-detail"
                  className={styles.detail}
                  aria-labelledby="monitor-component-name"
                >
                  <h3 id="monitor-component-name" className={styles.heading}>
                    {selected.name}
                  </h3>
                  {selected.service && (
                    <p className={styles.secondary}>
                      {selected.service.kind} · {t("rework.monitor.replicas", selected.service)}
                    </p>
                  )}
                  {selected.findings.length > 0 && (
                    <ul className={styles.findings}>
                      {selected.findings.map((finding) => (
                        <li key={finding.kind}>
                          <div className={styles.finding}>
                            <StatusBadge tone={finding.level} label={t(`rework.monitor.states.${finding.kind}`)} />
                            <span>
                              {t(`rework.monitor.findings.${finding.kind}`, {
                                ready: finding.ready,
                                desired: finding.desired,
                                time: finding.at ? time(finding.at) : "",
                                sources: finding.sources
                                  ?.map((source) => t(`rework.monitor.sources.${source}`))
                                  .join(", "),
                              })}
                              {finding.reason && ` (${finding.reason})`}
                            </span>
                          </div>
                          {finding.event && <p className={styles.secondary}>&quot;{finding.event}&quot;</p>}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              )}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
