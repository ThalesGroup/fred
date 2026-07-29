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
import { SERIES_COLORS } from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart.tsx";
import type { ResourceTypeStatsEntry } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { formatBytes } from "../../../../utils/formatBytes.ts";
import SizeByTypeBar from "./SizeByTypeBar.tsx";
import styles from "./ResourceStatsCards.module.css";

// Fixed categorical order (FRONT-09.I) — must stay pinned to the same bucket
// across renders, never cycled to whatever order the API returns.
const BUCKET_ORDER = ["pdf", "text", "ppt", "excel", "other"] as const;

// Explicit, meaning-carrying assignment (developer request, 2026-07-27) — not
// the generic sequential SERIES_COLORS slice used elsewhere: orange = PDF,
// blue = Texte, red = PPT, green = Excel/CSV, grey = Autres.
const BUCKET_COLOR: Record<(typeof BUCKET_ORDER)[number], string> = {
  pdf: SERIES_COLORS[1], // orange
  text: SERIES_COLORS[0], // blue
  ppt: SERIES_COLORS[8], // red
  excel: SERIES_COLORS[2], // green
  other: SERIES_COLORS[9], // grey
};

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
  const sizeSegments = BUCKET_ORDER.map((bucket) => ({
    key: bucket,
    label: t(`rework.resources.stats.bucket.${bucket}`),
    value: byBucket.get(bucket)?.size_bytes ?? 0,
    color: BUCKET_COLOR[bucket],
  }));

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
      <SizeByTypeBar
        title={t("rework.resources.stats.sizeByType.title")}
        tooltipTitle={t("rework.resources.stats.sizeByType.tooltipTitle")}
        segments={sizeSegments}
        isLoading={isLoading}
        isError={isError}
        formatValue={formatBytes}
      />
    </div>
  );
}
