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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { HomePeriod } from "../HomePage.tsx";
import styles from "./ActivityKpis.module.scss";

interface Kpi {
  key: "conversations" | "messages" | "agents";
  value: string;
  /** Percentage change vs the previous same-length period; sign drives direction. */
  delta: number;
}

// PLACEHOLDER DATA — activity counts and their period-over-period deltas need
// user-scoped KPI presets (messages_over_time, sessions_over_time,
// top_agents_by_conversations). Static example values per period for the
// prototype; swap for real queries before shipping.
const KPIS_BY_PERIOD: Record<HomePeriod, Kpi[]> = {
  7: [
    { key: "conversations", value: "24", delta: 18 },
    { key: "messages", value: "312", delta: 9 },
    { key: "agents", value: "7", delta: 0 },
  ],
  30: [
    { key: "conversations", value: "96", delta: 11 },
    { key: "messages", value: "1 280", delta: 14 },
    { key: "agents", value: "11", delta: 22 },
  ],
  90: [
    { key: "conversations", value: "264", delta: 7 },
    { key: "messages", value: "3 620", delta: -5 },
    { key: "agents", value: "14", delta: 8 },
  ],
};

interface ActivityKpisProps {
  period: HomePeriod;
}

/** Home page — top row of activity indicators (new conversations, messages
 * sent, agents used) over the selected period, each with its change vs the
 * previous same-length period. */
export default function ActivityKpis({ period }: ActivityKpisProps) {
  const { t } = useTranslation();
  const kpis = KPIS_BY_PERIOD[period];

  return (
    <section className={styles.section} aria-label={t("rework.home.activity.title")}>
      <div className={styles.head}>
        <Icon category="outlined" type="show_chart" />
        <h2 className={styles.title}>{t("rework.home.activity.title")}</h2>
      </div>

      <div className={styles.grid}>
        {kpis.map((kpi) => {
          const dir = kpi.delta > 0 ? "up" : kpi.delta < 0 ? "down" : "flat";
          const deltaText =
            dir === "flat"
              ? t("rework.home.activity.deltaFlat")
              : t(`rework.home.activity.delta${dir === "up" ? "Up" : "Down"}`, { count: Math.abs(kpi.delta) });
          return (
            <div key={kpi.key} className={styles.card}>
              <div className={styles.top}>
                <span className={styles.label}>{t(`rework.home.activity.${kpi.key}`)}</span>
                <span className={`${styles.delta} ${styles[dir]}`} title={t("rework.home.activity.vsPrevious")}>
                  {deltaText}
                </span>
              </div>
              <div className={styles.value}>{kpi.value}</div>
              <div className={styles.caption}>{t("rework.home.activity.vsPrevious")}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
