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
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import MultiSeriesLineChart from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import { useAnalyticsActivityOverTimeQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { HandlerControlPlaneV1KpiPresetsAnalyticsActivityOverTimeGetApiArg as ActivityArgs } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { bucketSeries, formatValue } from "./analyticsFormat";
import { KPI_CACHE } from "./analyticsQuery";
import { KPI_TRENDS, trendPoints, type TrendId } from "./kpiTrend";
import styles from "./AnalyticsPage.module.css";

export type { ActivityArgs };

interface KpiTrendDialogProps {
  id: TrendId;
  /** The tile's label: the dialog title and the series name. */
  label: string;
  /** The tile's period value, quoted under a distinct count. */
  value: number | null | undefined;
  /** The tab's own activity arguments, so the read shares its cache. */
  args: ActivityArgs;
  open: boolean;
  onClose: () => void;
}

/** A KPI over the selected period: a running total, or a count per bucket for distinct people. */
export default function KpiTrendDialog({ id, label, value, args, open, onClose }: KpiTrendDialogProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const activity = useAnalyticsActivityOverTimeQuery(args, { ...KPI_CACHE, skip: !open });
  const { kind, format } = KPI_TRENDS[id];
  const bucket = activity.data?.bucket ?? "day";
  const points = trendPoints(activity.data?.points, id);

  return (
    <Dialog
      open={open}
      title={label}
      confirmLabel={t("common.close")}
      onConfirm={onClose}
      onCancel={onClose}
      hideCancel
      maxWidth={880}
    >
      <MultiSeriesLineChart
        title={t(`rework.analytics.trend.title.${kind}.${bucket}`)}
        rows={bucketSeries(points, bucket, { trend: label }, lng, t)}
        series={[label]}
        seriesColors={["--primary"]}
        formatValue={(v) => formatValue(v, format, lng)}
        labelled
        flat
        isFetching={activity.isFetching}
        isLoading={activity.isLoading}
        isError={activity.isError}
      />
      {kind === "distinct" && value != null && (
        <p className={styles.note}>
          {t(`rework.analytics.trend.distinctNote.${id}`, { value: formatValue(value, format, lng) })}
        </p>
      )}
    </Dialog>
  );
}
