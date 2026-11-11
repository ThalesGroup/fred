// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useTranslation } from "react-i18next";
import type { AnalyticsCohortRow } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { InfoHint } from "./AnalyticsSection";
import { formatValue, NO_VALUE } from "./analyticsFormat";
import styles from "./AnalyticsPage.module.css";

const KEY = "rework.analytics.tables.cohorts";

/** Shade steps of a return share, darkest for the best rows. */
export function cohortLevel(share: number): "high" | "good" | "fair" | "low" {
  return share >= 0.6 ? "high" : share >= 0.45 ? "good" : share >= 0.3 ? "fair" : "low";
}

/** "2026-10" as the viewer's month name and year. */
export function formatCohortMonth(month: string, lng: string): string {
  const [year, number] = month.split("-").map(Number);
  return new Intl.DateTimeFormat(lng, { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(year, number - 1, 1)),
  );
}

interface CohortTableProps {
  rows: AnalyticsCohortRow[] | undefined;
  isLoading: boolean;
  isError: boolean;
}

/** One row per arrival month: its newcomers and their return 1, 2 and 3 months later. */
export default function CohortTable({ rows, isLoading, isError }: CohortTableProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const title = t(`${KEY}.title`);
  const offsets = [1, 2, 3];
  return (
    <section className={styles.cohorts} aria-label={title}>
      <div className={styles.blockHeader}>
        <h3 className={styles.blockTitle}>{title}</h3>
        <InfoHint label={title} def={t(`${KEY}.def`)} how={t(`${KEY}.how`)} />
      </div>
      {isError ? (
        <p role="alert" className={styles.note}>
          {t("common.loadingError")}
        </p>
      ) : isLoading ? (
        <p role="status" className={styles.note}>
          {t("common.loading")}
        </p>
      ) : !rows?.some((row) => row.size > 0) ? (
        <p role="status" className={styles.note}>
          {t(`${KEY}.empty`)}
        </p>
      ) : (
        <div className={styles.cohortScroll}>
          <table className={styles.cohortTable}>
            <thead>
              <tr>
                <th scope="col">{t(`${KEY}.month`)}</th>
                <th scope="col" className={styles.cohortNumber}>
                  {t(`${KEY}.size`)}
                </th>
                {offsets.map((n) => (
                  <th key={n} scope="col" className={styles.cohortCell}>
                    {t(`${KEY}.monthPlus`, { n })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.month}>
                  <th scope="row">{formatCohortMonth(row.month, lng)}</th>
                  <td className={styles.cohortNumber}>{formatValue(row.size, "count", lng)}</td>
                  {offsets.map((n, i) => {
                    const share = row.returns[i];
                    return share == null ? (
                      <td key={n} className={styles.cohortCell} data-level="none" aria-label={t(`${KEY}.notYet`)}>
                        {NO_VALUE}
                      </td>
                    ) : (
                      <td key={n} className={styles.cohortCell} data-level={cohortLevel(share)}>
                        {formatValue(share, "percent", lng)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
