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
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { IconType } from "@shared/utils/Type.ts";
import type { HomePeriod } from "../HomePage.tsx";
import styles from "./ResponsibleAiSection.module.scss";

type IndicatorTone = "warn" | "info" | "eco";

interface Indicator {
  tone: IndicatorTone;
  icon: IconType;
  value: string;
  caption: string;
  action?: string;
  /** Shows the "delete all unused conversations" affordance on this tile. */
  cleanup?: boolean;
}

// PLACEHOLDER DATA — these metrics need aggregation the frontend doesn't have
// yet: inactive-session and unused-file counts (control-plane / knowledge-flow),
// token usage over the period (KPI preset `user_token_usage_over_time`), and a
// derived CO2 estimate. Wired to static example values for the prototype; swap
// for real period-scoped queries before shipping.
//
// The period (7/30/90 j) is the LOOK-BACK WINDOW, not the inactivity threshold:
// - a conversation is "inactive" after 5 days with no activity (hardcoded here,
//   to be made configurable later),
// - a file is "unused" after 15 days without being used (hardcoded, likewise).
// Widening the window can only add matches, so these counts are monotonic
// non-decreasing as the period grows.
const INDICATORS_BY_PERIOD: Record<HomePeriod, Indicator[]> = {
  7: [
    {
      tone: "warn",
      icon: "forum",
      value: "4 conversations",
      caption: "sans activité depuis plus de 5 jours",
      action: "Faire le tri pour alléger la plateforme",
      cleanup: true,
    },
    {
      tone: "warn",
      icon: "description",
      value: "6 fichiers · 90 Mo",
      caption: "jamais utilisés depuis plus de 15 jours",
      action: "Supprimer pour libérer votre stockage",
    },
    { tone: "info", icon: "show_chart", value: "280 k tokens", caption: "consommés sur les 7 derniers jours" },
    { tone: "eco", icon: "cloud", value: "≈ 26 g CO₂e · 0,2 kWh", caption: "empreinte estimée de vos échanges" },
  ],
  30: [
    {
      tone: "warn",
      icon: "forum",
      value: "17 conversations",
      caption: "sans activité depuis plus de 5 jours",
      action: "Faire le tri pour alléger la plateforme",
      cleanup: true,
    },
    {
      tone: "warn",
      icon: "description",
      value: "19 fichiers · 260 Mo",
      caption: "jamais utilisés depuis plus de 15 jours",
      action: "Supprimer pour libérer votre stockage",
    },
    { tone: "info", icon: "show_chart", value: "1,2 M tokens", caption: "consommés sur les 30 derniers jours" },
    { tone: "eco", icon: "cloud", value: "≈ 110 g CO₂e · 0,9 kWh", caption: "empreinte estimée de vos échanges" },
  ],
  90: [
    {
      tone: "warn",
      icon: "forum",
      value: "39 conversations",
      caption: "sans activité depuis plus de 5 jours",
      action: "Faire le tri pour alléger la plateforme",
      cleanup: true,
    },
    {
      tone: "warn",
      icon: "description",
      value: "37 fichiers · 540 Mo",
      caption: "jamais utilisés depuis plus de 15 jours",
      action: "Supprimer pour libérer votre stockage",
    },
    { tone: "info", icon: "show_chart", value: "3,4 M tokens", caption: "consommés sur les 90 derniers jours" },
    { tone: "eco", icon: "cloud", value: "≈ 320 g CO₂e · 2,6 kWh", caption: "empreinte estimée de vos échanges" },
  ],
};

interface ResponsibleAiSectionProps {
  period: HomePeriod;
}

/** Home page — "IA responsable": nudges the user toward sober, responsible use
 * (clean up stale conversations/files, watch token usage and footprint) over
 * the selected period. */
export default function ResponsibleAiSection({ period }: ResponsibleAiSectionProps) {
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { showSuccess } = useToast();
  const indicators = INDICATORS_BY_PERIOD[period];

  const handleCleanup = () => {
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.home.responsible.cleanup.title"),
      message: t("rework.home.responsible.cleanup.message"),
      confirmButtonLabel: t("rework.home.responsible.cleanup.confirm"),
      onConfirm: () => {
        // PLACEHOLDER: no bulk "delete inactive conversations" endpoint exists
        // yet. Wire it (personal space + every team, > 5 days inactive) here.
        showSuccess({ summary: t("rework.home.responsible.cleanup.toast") });
      },
    });
  };

  return (
    <section className={styles.section} aria-label={t("rework.home.responsible.title")}>
      <div className={styles.head}>
        <Icon category="outlined" type="auto_awesome" />
        <h2 className={styles.title}>{t("rework.home.responsible.title")}</h2>
      </div>

      <div className={styles.card}>
        <div className={styles.grid}>
          {indicators.map((ind) => (
            <div key={ind.value} className={styles.ind}>
              <span className={styles.ic}>
                <Icon category="outlined" type={ind.icon} />
              </span>
              <div className={styles.body}>
                <div className={styles.value}>{ind.value}</div>
                <div className={styles.caption}>{ind.caption}</div>
                {ind.action && (
                  <div className={styles.action}>
                    <span className={styles.actionIcon}>
                      <Icon category="outlined" type="lightbulb" />
                    </span>
                    <span>{ind.action}</span>
                  </div>
                )}
              </div>
              {ind.cleanup && (
                <Tooltip text={t("rework.home.responsible.cleanup.aria")}>
                  <IconButton
                    size="small"
                    color="error"
                    variant="icon"
                    icon={{ category: "outlined", type: "delete_forever" }}
                    aria-label={t("rework.home.responsible.cleanup.aria")}
                    onClick={handleCleanup}
                  />
                </Tooltip>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
