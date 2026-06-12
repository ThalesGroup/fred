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
import type { ActiveUsersOverTimeRow } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import IconButton from "@shared/atoms/IconButton/IconButton";
import styles from "./AnalyticsPage.module.css";

interface ActiveUsersChartProps {
  rows: ActiveUsersOverTimeRow[];
  interval?: string;
  isFetching: boolean;
  isLoading: boolean;
  isError: boolean;
  onRefresh: () => void;
}

function BarChart({ rows }: { rows: ActiveUsersOverTimeRow[] }) {
  const max = Math.max(...rows.map((r) => r.unique_users), 1);

  return (
    <div className={styles.chart}>
      {rows.map((row) => (
        <div key={row.date} className={styles.bar}>
          <span className={styles.barValue}>{row.unique_users > 0 ? row.unique_users : ""}</span>
          <div
            className={styles.barFill}
            style={{ height: `${(row.unique_users / max) * 100}%` }}
            title={`${row.unique_users}`}
          />
          <span className={styles.barLabel}>{row.date}</span>
        </div>
      ))}
    </div>
  );
}

export default function ActiveUsersChart({
  rows,
  interval,
  isFetching,
  isLoading,
  isError,
  onRefresh,
}: ActiveUsersChartProps) {
  const { t } = useTranslation();

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>
          {t("rework.analytics.activeUsers.title")}
          {interval && <span className={styles.intervalBadge}>{interval}</span>}
        </h2>
        <IconButton
          color="primary"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "refresh" }}
          onClick={onRefresh}
          disabled={isFetching}
          title={t("rework.analytics.refresh")}
        />
      </div>

      {isLoading && !rows.length && <div className={styles.state}>{t("rework.analytics.loading")}</div>}
      {isFetching && !!rows.length && <div className={styles.state}>{t("rework.analytics.refreshing")}</div>}
      {isError && <div className={styles.stateError}>{t("rework.analytics.error")}</div>}
      {!!rows.length && <BarChart rows={rows} />}
    </section>
  );
}
