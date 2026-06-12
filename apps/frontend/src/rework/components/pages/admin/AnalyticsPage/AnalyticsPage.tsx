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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./AnalyticsPage.module.css";
import { useActiveUsersOverTimeQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { TIME_PRESETS } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import IconButton from "@shared/atoms/IconButton/IconButton";

const defaultPreset = TIME_PRESETS.find((p) => p.key === "last30d")!;
const defaultRange: TimeRange = { ...defaultPreset.resolve(), presetKey: "last30d" };

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultRange);
  const [refreshKey, setRefreshKey] = useState(0);

  const { data, isLoading, isFetching, isError } = useActiveUsersOverTimeQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: true },
  );

  const handleRangeChange = (range: TimeRange) => {
    setTimeRange(range);
    setRefreshKey((k) => k + 1);
  };

  const handleRefresh = () => {
    if (timeRange.presetKey) {
      const preset = TIME_PRESETS.find((p) => p.key === timeRange.presetKey)!;
      setTimeRange({ ...preset.resolve(), presetKey: timeRange.presetKey });
    }
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.analytics.title")}</h1>
        <div className={styles.headerControls}>
          <TimeRangeSelector value={timeRange} onChange={handleRangeChange} />
          <IconButton
            color="primary"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "refresh" }}
            onClick={handleRefresh}
            disabled={isFetching}
            title={t("common.refresh")}
          />
        </div>
      </div>

      <TimeSeriesLineChart
        key={refreshKey}
        title={t("rework.analytics.activeUsers.title")}
        rows={data?.rows ?? []}
        interval={data?.interval}
        valueLabel={t("rework.analytics.activeUsers.valueLabel")}
        isFetching={isFetching}
        isLoading={isLoading}
        isError={isError}
      />
    </div>
  );
}
