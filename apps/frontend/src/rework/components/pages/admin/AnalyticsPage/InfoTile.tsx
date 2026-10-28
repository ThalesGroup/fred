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
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import type { KpiStatCardProps } from "@shared/molecules/KpiStatCard/KpiStatCard";
import type { PeriodValue } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { HintContent, useInSection } from "./AnalyticsSection";
import { type DeltaKind, formatValue, periodDelta, type ValueFormat } from "./analyticsFormat";
import KpiTrendDialog, { type ActivityArgs } from "./KpiTrendDialog";
import { isTrendId } from "./kpiTrend";

type InfoTileProps = Omit<KpiStatCardProps, "label" | "hint" | "caption"> & {
  /** Names the tile's keys under `rework.analytics.tiles`. */
  id: string;
  caption?: string;
  /** Drop the "How to read it" line where it would point at the tab already shown. */
  withHow?: boolean;
  /** Period and previous period: the tile shows the first and its change. */
  period?: PeriodValue | null;
  format?: ValueFormat;
  deltaKind?: DeltaKind;
  lowerIsBetter?: boolean;
  /** A change that is neither good nor bad in itself, like a cost. */
  neutralDelta?: boolean;
  /** The tab's activity arguments: a tile with a per-bucket series then offers its trend. */
  trendArgs?: ActivityArgs;
};

/** A KPI tile whose label, caption and definition come from the analytics catalog. */
export default function InfoTile({
  id,
  caption,
  withHow = true,
  period,
  format,
  deltaKind = "relative",
  lowerIsBetter,
  neutralDelta,
  trendArgs,
  ...card
}: InfoTileProps) {
  const { t, i18n } = useTranslation();
  const [trendOpen, setTrendOpen] = useState(false);
  const nested = useInSection();
  const key = `rework.analytics.tiles.${id}`;
  const how = withHow ? t(`${key}.how`, { defaultValue: "" }) : "";
  const value = period !== undefined ? period?.current : card.value;
  const delta =
    period != null
      ? periodDelta(period, deltaKind, t, i18n.language, { lowerIsBetter, neutral: neutralDelta })
      : undefined;
  const label = t(`${key}.label`);
  const trendId = trendArgs && isTrendId(id) ? id : undefined;
  return (
    <>
      <KpiStatCard
        nested={nested}
        {...card}
        value={value}
        displayValue={
          value != null && (format || period !== undefined)
            ? formatValue(value, format ?? "count", i18n.language)
            : undefined
        }
        deltaLabel={delta?.label}
        deltaTone={delta?.tone}
        deltaDirection={delta?.direction}
        unavailable={card.unavailable ?? (period !== undefined && !card.isLoading && value == null)}
        label={label}
        caption={caption ?? t(`${key}.caption`, { defaultValue: "" })}
        hint={<HintContent def={t(`${key}.def`)} how={how || undefined} />}
        trendAction={trendId && { label: t("rework.analytics.trend.show"), onClick: () => setTrendOpen(true) }}
      />
      {trendId && trendArgs && (
        <KpiTrendDialog
          id={trendId}
          label={label}
          value={value}
          args={trendArgs}
          open={trendOpen}
          onClose={() => setTrendOpen(false)}
        />
      )}
    </>
  );
}
