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

// Renders inline, next to any token-usage widget — never as a separate panel
// (KPI-ANALYTICS-RFC.md §2.7). CO2e/kWh are shown unconditionally (essential);
// $ cost sits behind the Disclosure atom (optional/collapsible, secondary).
// One component reused at every scope (platform, team, personal) that shows
// token usage, so the same figures aren't computed three times over.

import { useTranslation } from "react-i18next";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import styles from "./TokenUsageImpact.module.css";

interface ImpactRow {
  co2e_grams?: number | null;
  kwh?: number | null;
  cost_usd?: number | null;
}

interface TokenUsageImpactProps {
  rows: ImpactRow[] | undefined;
  isLoading: boolean;
}

export default function TokenUsageImpact({ rows, isLoading }: TokenUsageImpactProps) {
  const { t } = useTranslation();

  if (isLoading || !rows || rows.length === 0) return null;

  const co2eGrams = rows.reduce((acc, r) => acc + (r.co2e_grams ?? 0), 0);
  const kwh = rows.reduce((acc, r) => acc + (r.kwh ?? 0), 0);
  const costUsd = rows.reduce((acc, r) => acc + (r.cost_usd ?? 0), 0);

  return (
    <div className={styles.impact}>
      <span className={styles.estimate}>
        {t("rework.tokenUsageImpact.summary", { co2e: co2eGrams.toFixed(1), kwh: kwh.toFixed(2) })}
      </span>
      <Disclosure title={t("rework.tokenUsageImpact.costTitle")}>
        <span className={styles.cost}>{t("rework.tokenUsageImpact.costValue", { cost: costUsd.toFixed(4) })}</span>
      </Disclosure>
    </div>
  );
}
