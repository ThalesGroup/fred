// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import { formatBytes } from "@shared/utils/formatBytes";
import type { Role, SupervisionCounts } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./OrganizationSupervisionPage.module.css";

const roles: Role[] = ["member", "editor", "admin", "analyst", "organization_owner", "personal_space_creator"];

export default function SupervisionCountsView({
  counts,
  compact = false,
}: {
  counts: SupervisionCounts;
  compact?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const number = (value: number) => value.toLocaleString(i18n.language);
  const label = (key: string) => t(`rework.supervision.${key}`);
  const published = counts.published;
  return (
    <>
      <div className={styles.cards}>
        {(
          [
            ["documents", counts.active.documents],
            ["vectors", published.vectors],
            ["datasets", published.tabular_datasets],
          ] as const
        ).map(([key, value]) => (
          <KpiStatCard key={key} label={label(key)} value={value} isLoading={false} isError={false} />
        ))}
      </div>
      <p>
        {label("volume")}: {formatBytes(counts.active.bytes, i18n.language)}
      </p>
      <Disclosure title={label("complementary")} defaultOpen={!compact}>
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
        <h3>{label("roles")}</h3>
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
    </>
  );
}
