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
  /** Percentage change vs the previous same-length window; sign drives direction. */
  delta: number;
}

// PLACEHOLDER DATA — static example values per period for the prototype; swap
// for real user-scoped queries before shipping.
//
// Trend chip = trailing-window vs previous equal-length window (validated
// design). For today = D and a selected period of N days:
//   - value ("current")  = sum/count over [D-N, D]
//   - baseline ("prev")  = same metric over [D-2N, D-N]
//   - delta% = round((current - prev) / prev * 100); the sign drives ▲/▼.
// So 7 j compares the last 7 days to the 7 days before, 30 j the last 30 to the
// prior 30, etc. — consistent with the "sur les X derniers jours" caption.
//
// Edge cases: prev == 0 && current > 0 -> show a "new" marker, not a %;
// prev == 0 && current == 0 -> flat (0%); round to an integer and optionally
// cap the displayed magnitude (e.g. ">999%").
//
// Per metric, over each window:
//   - conversations -> count of sessions created (sessions_over_time)
//   - messages      -> count of messages sent (messages_over_time)
//   - agents        -> count of DISTINCT agents used (not a plain sum;
//                      derive from top_agents_by_conversations / a distinct
//                      user-scoped aggregation)
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
              <div className={styles.caption}>{t("rework.home.activity.periodCaption", { count: period })}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
