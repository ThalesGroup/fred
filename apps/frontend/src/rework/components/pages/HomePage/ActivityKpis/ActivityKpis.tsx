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
import type { AnalyticsResponse } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { HomePeriod } from "../HomePage";
import styles from "./ActivityKpis.module.scss";

interface ActivityKpisProps {
  period: HomePeriod;
  sessions?: AnalyticsResponse["results"];
  turns?: AnalyticsResponse["results"];
  sessionStatus?: string;
  turnStatus?: string;
}

export default function ActivityKpis({ period, sessions, turns, sessionStatus, turnStatus }: ActivityKpisProps) {
  const { t, i18n } = useTranslation();
  const signed = (value: bigint) => `${value > 0n ? "+" : ""}${value.toLocaleString(i18n.language)}`;
  const kpis = [
    { key: "conversations", measure: "activity.retained_conversations", data: sessions, status: sessionStatus },
    { key: "messages", measure: "activity.completed_turns", data: turns, status: turnStatus },
    { key: "agents", measure: "activity.agents_used", data: turns, status: turnStatus },
  ];
  return (
    <section className={styles.section} aria-label={t("rework.home.activity.title")}>
      <div className={styles.head}>
        <Icon category="outlined" type="show_chart" />
        <h2 className={styles.title}>{t("rework.home.activity.title")}</h2>
      </div>
      <div className={styles.grid}>
        {kpis.map(({ key, measure, data, status }) => {
          const raw = status ? undefined : data?.current?.rows[0]?.values[measure];
          const prior = status ? undefined : data?.previous?.rows[0]?.values[measure];
          const value = raw === undefined ? undefined : BigInt(raw);
          const previous = prior === undefined ? undefined : BigInt(prior);
          let direction: "up" | "down" | "flat" = "flat";
          let deltaText: string | undefined;
          if (value !== undefined && previous !== undefined) {
            const delta = value - previous;
            direction = delta > 0n ? "up" : delta < 0n ? "down" : "flat";
            const magnitude = delta < 0n ? -delta : delta;
            // Round only the display percentage. Counts and subtraction remain exact integers.
            const pct = previous > 0n ? (magnitude * 200n + previous) / (2n * previous) : 0n;
            deltaText =
              delta === 0n
                ? t("rework.home.activity.deltaFlat")
                : previous === 0n
                  ? signed(delta)
                  : t(`rework.home.activity.delta${direction === "up" ? "Up" : "Down"}`, {
                      pct: pct > 500n ? ">500" : pct.toString(),
                      abs: signed(delta),
                    });
          }
          return (
            <div key={key} className={styles.card}>
              <div className={styles.top}>
                <span className={styles.label} title={t(`rework.home.activity.${key}Definition`)}>
                  {t(`rework.home.activity.${key}`)}
                </span>
                {deltaText !== undefined && (
                  <span className={`${styles.delta} ${styles[direction]}`} title={t("rework.home.activity.vsPrevious")}>
                    {deltaText}
                  </span>
                )}
              </div>
              <div className={styles.value}>
                {value?.toLocaleString(i18n.language) ?? (status === "loading" ? "…" : "—")}
              </div>
              {status && <p role="status">{t(`rework.home.activity.${status}`)}</p>}
              <div className={styles.caption}>{t("rework.home.activity.periodCaption", { count: period })}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
