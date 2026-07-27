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
import BarChart from "@shared/molecules/BarChart/BarChart.tsx";
import PieChart from "@shared/molecules/PieChart/PieChart.tsx";
import { SERIES_COLORS } from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart.tsx";
import type { ResourceTypeStatsEntry } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./ResourceStatsCards.module.css";

// Fixed categorical order (FRONT-09.I) — colors must stay pinned to the same
// bucket across renders, never cycled to whatever order the API returns.
const BUCKET_ORDER = ["pdf", "text", "ppt", "excel", "other"] as const;
const BUCKET_COLORS = SERIES_COLORS.slice(0, BUCKET_ORDER.length);

interface ResourceStatsCardsProps {
  entries: ResourceTypeStatsEntry[] | undefined;
  isLoading: boolean;
  isError: boolean;
}

export default function ResourceStatsCards({ entries, isLoading, isError }: ResourceStatsCardsProps) {
  const { t } = useTranslation();

  const byBucket = new Map((entries ?? []).map((entry) => [entry.bucket, entry]));
  const countRows = BUCKET_ORDER.map((bucket) => ({
    label: t(`rework.resources.stats.bucket.${bucket}`),
    value: byBucket.get(bucket)?.count ?? 0,
  }));
  // Zero-size buckets are dropped (an empty pie slice adds noise, not
  // signal), but color must stay pinned to its bucket — filter row and
  // color together, in lockstep, rather than re-deriving color from the
  // post-filter index.
  const sizeEntries = BUCKET_ORDER.map((bucket, i) => ({
    label: t(`rework.resources.stats.bucket.${bucket}`),
    value: byBucket.get(bucket)?.size_bytes ?? 0,
    color: BUCKET_COLORS[i],
  })).filter((entry) => entry.value > 0);
  const sizeRows = sizeEntries.map(({ label, value }) => ({ label, value }));
  const sizeColors = sizeEntries.map((entry) => entry.color);

  return (
    <div className={styles.grid}>
      <BarChart
        title={t("rework.resources.stats.filesByType.title")}
        rows={countRows}
        valueLabel={t("rework.resources.stats.filesByType.valueLabel")}
        isLoading={isLoading}
        isError={isError}
        orientation="vertical"
        sortOrder="none"
        compact
      />
      <PieChart
        title={t("rework.resources.stats.sizeByType.title")}
        rows={sizeRows}
        isLoading={isLoading}
        isError={isError}
        colors={sizeColors}
        compact
      />
    </div>
  );
}
