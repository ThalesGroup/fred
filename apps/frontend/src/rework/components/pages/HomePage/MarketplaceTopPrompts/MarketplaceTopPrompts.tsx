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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import {
  type MarketplacePromptSummary,
  useGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery,
  useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery,
  usePostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { HomePeriod } from "../HomePage.tsx";
import PromptViewDialog from "../../PromptsPage/PromptViewDialog/PromptViewDialog.tsx";
import Sparkline from "../Sparkline/Sparkline.tsx";
import styles from "./MarketplaceTopPrompts.module.scss";

const TOP_N = 8;

/**
 * Build a plausible 7-point "last 7 days" series ending at `total`.
 *
 * PLACEHOLDER: the marketplace usage counter (`session_count`) is a scalar — no
 * per-day history exists yet. This derives a smooth upward series from the
 * total so the trend line has something to draw; replace with a real 7-day
 * series once the backend exposes one (see #2317 follow-up).
 */
function mockWeekSeries(total: number): number[] {
  const start = Math.max(0, Math.round(total * 0.82));
  const step = (total - start) / 6;
  return Array.from({ length: 7 }, (_, i) => Math.round(start + step * i));
}

interface MarketplaceTopPromptsProps {
  period: HomePeriod;
}

/** Home page — Top 8 most-used community prompts with their (placeholder) usage
 * trend over the selected period. The prompt list and usage totals are real;
 * only the per-day series is mocked until a time-series endpoint exists. */
export default function MarketplaceTopPrompts({ period }: MarketplaceTopPromptsProps) {
  const { t } = useTranslation();
  const { data: prompts = [] } = useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery();
  const top = [...prompts].sort((a, b) => (b.session_count ?? 0) - (a.session_count ?? 0)).slice(0, TOP_N);

  const [viewingPrompt, setViewingPrompt] = useState<MarketplacePromptSummary | null>(null);
  const [recordUse] = usePostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostMutation();

  // Same read-only view as the marketplace: fetch the full text on demand when a
  // card is opened, guarding against a stale previous-prompt result.
  const { data: rawViewDetail } = useGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery(
    { promptId: viewingPrompt?.id || "" },
    { skip: !viewingPrompt },
  );
  const viewDetail = rawViewDetail && rawViewDetail.id === viewingPrompt?.id ? rawViewDetail : undefined;

  return (
    <section className={styles.section} aria-label={t("rework.home.topPrompts.title")}>
      <div className={styles.head}>
        <Icon category="outlined" type="storefront" />
        <h2 className={styles.title}>{t("rework.home.topPrompts.title")}</h2>
      </div>

      {top.length === 0 ? (
        <div className={styles.empty}>{t("rework.home.topPrompts.empty")}</div>
      ) : (
        <div className={styles.grid}>
          {top.map((prompt) => {
            const uses = prompt.session_count ?? 0;
            const series = mockWeekSeries(uses);
            const weekDelta = series[series.length - 1] - series[0];
            return (
              <div
                key={prompt.id}
                className={styles.card}
                role="button"
                tabIndex={0}
                onClick={() => setViewingPrompt(prompt)}
                onKeyDown={(e) => e.key === "Enter" && setViewingPrompt(prompt)}
              >
                <span className={styles.team}>{prompt.team_name}</span>
                <span className={styles.name}>{prompt.name}</span>
                <div className={styles.foot}>
                  <div>
                    <div className={styles.uses}>
                      <span className={styles.usesNum}>{uses.toLocaleString("fr-FR")}</span>{" "}
                      <span className={styles.usesLbl}>{t("rework.home.topPrompts.uses")}</span>
                    </div>
                    <div className={styles.delta}>
                      {t("rework.home.topPrompts.periodDelta", { count: weekDelta, days: period })}
                    </div>
                  </div>
                  <Sparkline values={series} color="var(--success)" />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <PromptViewDialog
        open={!!viewingPrompt}
        preloadedDetail={
          viewDetail
            ? {
                id: viewDetail.id,
                name: viewDetail.name,
                description: viewDetail.description,
                text: viewDetail.text,
              }
            : null
        }
        chipLabel={viewingPrompt?.team_name ?? null}
        onCopied={() => {
          if (viewingPrompt) recordUse({ promptId: viewingPrompt.id });
        }}
        onClose={() => setViewingPrompt(null)}
      />
    </section>
  );
}
