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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import {
  useUserAgentsUsedTotalQuery,
  useUserMessagesTotalQuery,
  useUserSessionsTotalQuery,
  useUserTokenUsageOverTimeQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { HomePeriod } from "../HomePage.tsx";
import { formatCompactTokens, homePeriodRange } from "../homePeriod.ts";
import styles from "./ActivityKpis.module.scss";

const numberFmt = new Intl.NumberFormat("fr-FR");

type KpiKey = "conversations" | "messages" | "agents" | "tokens";
type Direction = "up" | "down" | "flat" | "new";

interface KpiView {
  key: KpiKey;
  value: string;
  dir: Direction;
  /** Absolute percentage magnitude, capped, for the up/down chips only. */
  magnitude: number;
  /** Signed absolute change vs the previous window, shown alongside the % (and
   * used as the "+N" jump when there's no baseline). */
  delta: number;
  /** Tokens have no period-over-period delta preset, so that card shows the
   * value alone — no trend chip. Defaults to shown. */
  showTrend?: boolean;
}

// Each preset returns { value, delta } where value = count over [D-N, D] and
// delta = value − count over the previous equal window [D-2N, D-N] (validated
// design, backend query_user_*_total). We turn that absolute delta into the
// ▲/▼ % chip here — one place, so the backend stays on the same "value + net
// change" contract as every other scalar preset:
//   prev = value − delta
//   prev > 0  → pct = round(delta / prev × 100), sign drives ▲/▼, capped ±999
//   prev == 0 && value > 0 → "new": no meaningful % (would divide by zero), so
//                            show the absolute jump instead (e.g. "+244")
//   prev == 0 && value == 0 → flat
type KpiQuery = {
  data?: { value?: number | null; delta?: number | null } | undefined;
  isLoading: boolean;
  isError: boolean;
};

function buildKpi(key: KpiKey, q: KpiQuery): KpiView {
  if (q.isLoading) return { key, value: "…", dir: "flat", magnitude: 0, delta: 0 };
  const value = q.data?.value;
  if (q.isError || value == null) return { key, value: "—", dir: "flat", magnitude: 0, delta: 0 };

  const delta = q.data?.delta ?? 0;
  const prev = value - delta;
  let dir: Direction = "flat";
  let magnitude = 0;
  if (prev <= 0) {
    // No baseline to compare against — carry the absolute count so the chip can
    // read "+244" rather than an undefined percentage.
    if (value > 0) {
      dir = "new";
      magnitude = value;
    }
  } else {
    const pct = Math.round((delta / prev) * 100);
    if (pct > 0) {
      dir = "up";
      magnitude = Math.min(pct, 999);
    } else if (pct < 0) {
      dir = "down";
      magnitude = Math.min(Math.abs(pct), 999);
    }
  }
  return { key, value: numberFmt.format(value), dir, magnitude, delta };
}

/** Signed absolute change, e.g. "+244" / "-133". */
function formatSignedDelta(delta: number): string {
  return delta > 0 ? `+${numberFmt.format(delta)}` : numberFmt.format(delta);
}

interface ActivityKpisProps {
  period: HomePeriod;
}

/** Home page — top row of activity indicators (new conversations, messages
 * sent, agents used) over the selected period, each with its change vs the
 * previous same-length period. Live: self-scoped KPI presets (#2298). */
export default function ActivityKpis({ period }: ActivityKpisProps) {
  const { t } = useTranslation();

  // Memoise the range on `period`: a fresh `until` every render would change
  // the RTK Query cache key and refetch in a loop. TTL 300s (KPI-ANALYTICS-RFC
  // §2.6), same as the analytics pages.
  const range = useMemo(() => homePeriodRange(period), [period]);
  const opts = { refetchOnMountOrArgChange: 300 };
  const sessions = useUserSessionsTotalQuery(range, opts);
  const messages = useUserMessagesTotalQuery(range, opts);
  const agents = useUserAgentsUsedTotalQuery(range, opts);
  // Tokens come from the time-series preset (no scalar+delta), so this card is
  // the running total over the period without a trend chip.
  const tokens = useUserTokenUsageOverTimeQuery(range, opts);
  const tokensValue = tokens.isLoading
    ? "…"
    : tokens.isError
      ? "—"
      : formatCompactTokens((tokens.data?.rows ?? []).reduce((sum, r) => sum + (r.value ?? 0), 0));

  const kpis: KpiView[] = [
    buildKpi("conversations", sessions),
    buildKpi("messages", messages),
    buildKpi("agents", agents),
    { key: "tokens", value: tokensValue, dir: "flat", magnitude: 0, delta: 0, showTrend: false },
  ];

  return (
    <section className={styles.section} aria-label={t("rework.home.activity.title")}>
      <div className={styles.head}>
        <Icon category="outlined" type="show_chart" />
        <h2 className={styles.title}>{t("rework.home.activity.title")}</h2>
      </div>

      <div className={styles.grid}>
        {kpis.map((kpi) => {
          const showTrend = kpi.showTrend !== false;
          // Every chip shares the neutral secondary styling; "new" reuses one.
          const styleClass = kpi.dir === "new" ? styles.up : styles[kpi.dir];
          const deltaText =
            kpi.dir === "flat"
              ? t("rework.home.activity.deltaFlat")
              : kpi.dir === "new"
                ? formatSignedDelta(kpi.delta)
                : t(`rework.home.activity.delta${kpi.dir === "up" ? "Up" : "Down"}`, {
                    count: kpi.magnitude,
                    abs: formatSignedDelta(kpi.delta),
                  });
          return (
            <div key={kpi.key} className={styles.card}>
              <div className={styles.top}>
                <span className={styles.label}>{t(`rework.home.activity.${kpi.key}`)}</span>
                {showTrend && (
                  <span className={`${styles.delta} ${styleClass}`} title={t("rework.home.activity.vsPrevious")}>
                    {deltaText}
                  </span>
                )}
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
