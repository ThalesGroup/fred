// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import { formatBytes } from "@shared/utils/formatBytes";
import type { Role, SupervisionCounts } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./OrganizationSupervisionPage.module.css";

const roles: Role[] = ["member", "editor", "admin", "analyst", "organization_owner"];

export function SupervisionSummary({ counts, activeTeams }: { counts: SupervisionCounts; activeTeams?: number }) {
  const { t, i18n } = useTranslation();
  const label = (key: string) => t(`rework.supervision.${key}`);
  const number = (value: number) => value.toLocaleString(i18n.language);
  const metrics: [string, string][] = [
    ...(activeTeams === undefined ? [] : [["activeTeams", number(activeTeams)] as [string, string]]),
    ["documents", number(counts.active.documents)],
    ["vectors", number(counts.published.vectors)],
    ["datasets", number(counts.published.tabular_datasets)],
    ["volume", formatBytes(counts.active.bytes, i18n.language)],
  ];
  return (
    <div className={styles.summary}>
      <dl className={styles.metrics}>
        {metrics.map(([key, value]) => (
          <div key={key}>
            <dt>{label(key)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <div className={styles.states}>
        {(
          [
            ["failed", counts.failed_documents, "error"],
            ["processing", counts.processing.reduce((sum, item) => sum + item.documents, 0), "info"],
            ["purgeDocuments", counts.pending_purge.documents, "warning"],
          ] as const
        ).map(([key, value, tone]) => (
          <div key={key}>
            <span>{label(key)}</span>
            <StatusBadge label={number(value)} tone={value > 0 ? tone : "neutral"} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SupervisionCountsView({ counts }: { counts: SupervisionCounts }) {
  const { t, i18n } = useTranslation();
  const number = (value: number) => value.toLocaleString(i18n.language);
  const label = (key: string) => t(`rework.supervision.${key}`);
  const published = counts.published;
  return (
    <div className={styles.details}>
      <dl className={styles.counts}>
        <dt>{label("publishedDocuments")}</dt>
        <dd>{number(published.documents)}</dd>
        <dt>{label("chunks")}</dt>
        <dd>{number(published.chunks)}</dd>
        <dt>{label("rows")}</dt>
        <dd>{published.total_rows === null ? label("unknown") : number(published.total_rows)}</dd>
        {published.total_rows === null && (
          <>
            <dt>{label("knownRows")}</dt>
            <dd>{number(published.known_rows)}</dd>
            <dt>{label("unknownDatasets")}</dt>
            <dd>{number(published.datasets_with_unknown_rows)}</dd>
          </>
        )}
        <dt>{label("failed")}</dt>
        <dd>{number(counts.failed_documents)}</dd>
        <dt>{label("purgeDocuments")}</dt>
        <dd>{number(counts.pending_purge.documents)}</dd>
        <dt>{label("purgeBytes")}</dt>
        <dd>{formatBytes(counts.pending_purge.bytes, i18n.language)}</dd>
        <dt>{label("users")}</dt>
        <dd>{number(counts.distinct_users)}</dd>
      </dl>
      <h3>{label("processing")}</h3>
      {counts.processing.length === 0 ? (
        <p>{label("noProcessing")}</p>
      ) : (
        <dl className={styles.counts}>
          {counts.processing.map((row) => (
            <div key={`${row.status}:${row.stage}`} className={styles.countRow}>
              <dt>
                {label(`statuses.${row.status}`)} / {label(`stages.${row.stage}`)}
              </dt>
              <dd>{number(row.documents)}</dd>
            </div>
          ))}
        </dl>
      )}
      <Disclosure title={label("roles")}>
        <p>{label("rolesHint")}</p>
        <dl className={styles.counts}>
          {roles.map((role) => (
            <div key={role} className={styles.countRow}>
              <dt>{label(`roleNames.${role}`)}</dt>
              <dd>{number(counts.direct_roles.find((item) => item.role === role)?.assignments ?? 0)}</dd>
            </div>
          ))}
        </dl>
      </Disclosure>
    </div>
  );
}
