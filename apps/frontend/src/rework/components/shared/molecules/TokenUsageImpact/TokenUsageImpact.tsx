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

import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import type { AnalyticsEstimate, AnalyticsRow } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import styles from "./TokenUsageImpact.module.css";

interface ImpactRow {
  co2e_grams?: number | null;
  kwh?: number | null;
  cost_usd?: number | null;
}

interface TokenUsageImpactProps {
  rows?: ImpactRow[];
  estimates?: AnalyticsRow["estimates"];
  isLoading: boolean;
  isError?: boolean;
}

function legacyEstimate(rows: ImpactRow[] | undefined, key: keyof ImpactRow): AnalyticsEstimate {
  const known = (rows ?? []).flatMap((row) => (row[key] == null || !Number.isFinite(row[key]) ? [] : [row[key]!]));
  const sum = known.reduce((a, b) => a + b, 0);
  return {
    value: known.length && Number.isFinite(sum) ? String(sum) : null,
    coverage: !known.length ? "unavailable" : known.length === rows?.length ? "complete" : "partial",
    fallback: false,
  };
}

export function formatImpactEstimate(
  estimate: AnalyticsEstimate | undefined,
  unit: string,
  locale: string,
  t: TFunction,
) {
  const value = estimate?.value == null ? undefined : Number(estimate.value);
  if (value === undefined || !Number.isFinite(value) || estimate?.coverage === "unavailable")
    return t("rework.tokenUsageImpact.unavailable");
  return `${value.toLocaleString(locale, { maximumFractionDigits: 6 })} ${unit}${estimate?.coverage === "partial" ? ` (${t("rework.tokenUsageImpact.partial")})` : ""}${estimate?.fallback ? ` (${t("rework.tokenUsageImpact.fallback")})` : ""}`;
}

export default function TokenUsageImpact({ rows, estimates, isLoading, isError = false }: TokenUsageImpactProps) {
  const { t, i18n } = useTranslation();
  const display = (estimate: AnalyticsEstimate | undefined, unit: string) =>
    formatImpactEstimate(estimate, unit, i18n.language, t);
  const co2e = estimates?.["usage.co2e_grams"] ?? (estimates ? undefined : legacyEstimate(rows, "co2e_grams"));
  const energy = estimates?.["usage.energy_kwh"] ?? (estimates ? undefined : legacyEstimate(rows, "kwh"));
  const cost = estimates?.["usage.cost_eur"] ?? (estimates ? undefined : legacyEstimate(rows, "cost_usd"));
  return (
    <div className={styles.impact}>
      {isError ? (
        <span role="alert">{t("common.loadingError")}</span>
      ) : isLoading ? (
        <span role="status">{t("common.loading")}</span>
      ) : (
        <>
          <span className={styles.estimate}>
            {t("rework.tokenUsageImpact.estimates")}: {display(co2e, "g CO2e")} · {display(energy, "kWh")}
          </span>
          <Disclosure title={t("rework.tokenUsageImpact.costTitle")}>
            <span className={styles.cost}>{display(cost, estimates ? "EUR" : "USD")}</span>
            {estimates && <p>{t("rework.tokenUsageImpact.staticFactors")}</p>}
          </Disclosure>
        </>
      )}
    </div>
  );
}
