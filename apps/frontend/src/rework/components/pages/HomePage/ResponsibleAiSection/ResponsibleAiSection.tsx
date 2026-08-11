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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { IconType } from "@shared/utils/Type.ts";
import { useUserTokenUsageOverTimeQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { HomePeriod } from "../HomePage.tsx";
import { formatCompactTokens, homePeriodRange } from "../homePeriod.ts";
import CleanupDialog, { type CleanupGroup } from "../CleanupDialog/CleanupDialog.tsx";
import styles from "./ResponsibleAiSection.module.scss";

const nf = (maximumFractionDigits: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits });

type IndicatorTone = "warn" | "info" | "eco";
type CleanupKind = "conversations" | "files";

interface Indicator {
  tone: IndicatorTone;
  icon: IconType;
  value: string;
  caption: string;
  /** Opens the matching cleanup tool from this tile. */
  cleanupKind?: CleanupKind;
  /** Shows an info button opening the footprint-methodology dialog. */
  info?: boolean;
}

// PLACEHOLDER DATA — the two cleanup indicators below (inactive conversations,
// unused personal files) still need aggregation the frontend doesn't have yet:
// inactive-session and unused-file counts (control-plane / knowledge-flow).
// Wired to static example values for the prototype; swap for real period-scoped
// queries before shipping. The tokens + footprint tiles, by contrast, are LIVE:
// built from the `user_token_usage_over_time` KPI preset (see below).
//
// The period (7/30/90 j) is the LOOK-BACK WINDOW, not the inactivity threshold:
// - a conversation is "inactive" after 5 days with no activity (hardcoded here,
//   to be made configurable later),
// - a file is "unused" after 15 days without being used (hardcoded, likewise).
// Widening the window can only add matches, so these counts are monotonic
// non-decreasing as the period grows.
//
// SCOPE — the "files" indicator counts the caller's PERSONAL space only
// (personal-<uid>): it is their own storage, freely deletable. Team files are
// deliberately excluded — they are shared, "unused" there is a collective (not
// personal) notion, and deletion is permission-gated. (Conversations, by
// contrast, span the personal space AND every team the user belongs to.)
const CLEANUP_INDICATORS_BY_PERIOD: Record<HomePeriod, Indicator[]> = {
  7: [
    {
      tone: "warn",
      icon: "forum",
      value: "4 conversations inactives",
      caption: "depuis plus de 5 jours",
      cleanupKind: "conversations",
    },
    {
      tone: "warn",
      icon: "description",
      value: "6 fichiers personnels non utilisés (90 Mo)",
      caption: "depuis plus de 15 jours",
      cleanupKind: "files",
    },
  ],
  30: [
    {
      tone: "warn",
      icon: "forum",
      value: "17 conversations inactives",
      caption: "depuis plus de 5 jours",
      cleanupKind: "conversations",
    },
    {
      tone: "warn",
      icon: "description",
      value: "19 fichiers personnels non utilisés (260 Mo)",
      caption: "depuis plus de 15 jours",
      cleanupKind: "files",
    },
  ],
  90: [
    {
      tone: "warn",
      icon: "forum",
      value: "39 conversations inactives",
      caption: "depuis plus de 5 jours",
      cleanupKind: "conversations",
    },
    {
      tone: "warn",
      icon: "description",
      value: "37 fichiers personnels non utilisés (540 Mo)",
      caption: "depuis plus de 15 jours",
      cleanupKind: "files",
    },
  ],
};

// PLACEHOLDER — the cleanup tools list example items. Real data: inactive
// sessions grouped by space (personal + each team), and unused personal files.
const INACTIVE_CONVERSATIONS: CleanupGroup[] = [
  {
    key: "personal",
    label: "Espace personnel",
    items: [
      { id: "c1", title: "Analyse d'appel d'offres — SNCF", meta: "Rédacteur AO" },
      { id: "c2", title: "Brainstorm nommage produit", meta: "Créatif" },
      { id: "c3", title: "Résumé de réunion Q2", meta: "Assistant réunion" },
    ],
  },
  {
    key: "bid",
    label: "Bid & Capture",
    items: [
      { id: "c4", title: "Réponse technique — Région Grand Est", meta: "Rédacteur AO" },
      { id: "c5", title: "Relecture du mémoire technique", meta: "Analyste documentaire" },
    ],
  },
  {
    key: "mkt",
    label: "Marketing",
    items: [{ id: "c6", title: "Idées de slogans — campagne été", meta: "Créatif" }],
  },
];

const UNUSED_FILES: CleanupGroup[] = [
  {
    key: "personal",
    label: "Espace personnel",
    items: [
      { id: "f1", title: "rapport-annuel-2024.pdf", meta: "18 Mo" },
      { id: "f2", title: "notes-brouillon.docx", meta: "2 Mo" },
      { id: "f3", title: "export-donnees-clients.xlsx", meta: "7 Mo" },
      { id: "f4", title: "presentation-produit-v1.pptx", meta: "24 Mo" },
    ],
  },
];

interface ResponsibleAiSectionProps {
  period: HomePeriod;
}

/** Home page — "IA responsable": nudges the user toward sober, responsible use
 * (clean up stale conversations/files, watch token usage and footprint) over
 * the selected period. */
export default function ResponsibleAiSection({ period }: ResponsibleAiSectionProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const [footprintInfoOpen, setFootprintInfoOpen] = useState(false);
  const [cleanupKind, setCleanupKind] = useState<CleanupKind | null>(null);

  // LIVE — personal token usage + its green-cost estimate over the period, from
  // the self-scoped `user_token_usage_over_time` preset (the server already
  // derives co2e/kwh per bucket). Memoise the range on `period`: a fresh `until`
  // every render would change the cache key and refetch in a loop. TTL 300s per
  // KPI-ANALYTICS-RFC.md §2.6, same as the analytics pages.
  const range = useMemo(() => homePeriodRange(period), [period]);
  const {
    data: usageData,
    isLoading: usageLoading,
    isError: usageError,
  } = useUserTokenUsageOverTimeQuery(range, { refetchOnMountOrArgChange: 300 });

  const usage = useMemo(() => {
    const rows = usageData?.rows ?? [];
    return {
      tokens: rows.reduce((acc, r) => acc + (r.value ?? 0), 0),
      co2e: rows.reduce((acc, r) => acc + (r.co2e_grams ?? 0), 0),
      kwh: rows.reduce((acc, r) => acc + (r.kwh ?? 0), 0),
    };
  }, [usageData]);

  // "…" while the first fetch resolves, "—" if the KPI service is unavailable
  // (OpenSearch down → 503); otherwise the real aggregate.
  const tokensValue = usageLoading ? "…" : usageError ? "—" : `${formatCompactTokens(usage.tokens)} tokens`;
  const footprintValue = usageLoading
    ? "…"
    : usageError
      ? "—"
      : `≈ ${nf(1).format(usage.co2e)} g CO₂e · ${nf(2).format(usage.kwh)} kWh`;

  const indicators: Indicator[] = [
    ...CLEANUP_INDICATORS_BY_PERIOD[period],
    { tone: "info", icon: "show_chart", value: tokensValue, caption: `consommés sur les ${period} derniers jours` },
    { tone: "eco", icon: "cloud", value: footprintValue, caption: "empreinte estimée de vos échanges", info: true },
  ];

  const isFiles = cleanupKind === "files";

  const handleCleanupConfirm = (ids: string[]) => {
    // PLACEHOLDER: no bulk delete endpoint exists yet. Wire the real deletion
    // (personal space + teams for conversations; personal space for files) here.
    showSuccess({ summary: t("rework.home.responsible.cleanupTool.toast", { count: ids.length }) });
    setCleanupKind(null);
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
            <div key={ind.icon} className={styles.ind}>
              <span className={styles.ic}>
                <Icon category="outlined" type={ind.icon} />
              </span>
              <div className={styles.body}>
                <div className={styles.value}>{ind.value}</div>
                <div className={styles.caption}>{ind.caption}</div>
              </div>
              {ind.cleanupKind && (
                <Tooltip text={t("rework.home.responsible.cleanupTool.aria")}>
                  <IconButton
                    size="small"
                    color="on-surface-retreat"
                    variant="icon"
                    icon={{ category: "outlined", type: "delete_sweep" }}
                    aria-label={t("rework.home.responsible.cleanupTool.aria")}
                    onClick={() => setCleanupKind(ind.cleanupKind ?? null)}
                  />
                </Tooltip>
              )}
              {ind.info && (
                <IconButton
                  size="small"
                  color="on-surface-retreat"
                  variant="icon"
                  icon={{ category: "outlined", type: "info" }}
                  aria-label={t("rework.home.responsible.footprintInfo.aria")}
                  onClick={() => setFootprintInfoOpen(true)}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      <CleanupDialog
        open={cleanupKind !== null}
        title={t(
          isFiles ? "rework.home.responsible.cleanupFiles.title" : "rework.home.responsible.cleanupConversations.title",
        )}
        subtitle={t(
          isFiles
            ? "rework.home.responsible.cleanupFiles.subtitle"
            : "rework.home.responsible.cleanupConversations.subtitle",
        )}
        groups={isFiles ? UNUSED_FILES : INACTIVE_CONVERSATIONS}
        emptyLabel={t(
          isFiles ? "rework.home.responsible.cleanupFiles.empty" : "rework.home.responsible.cleanupConversations.empty",
        )}
        onConfirm={handleCleanupConfirm}
        onClose={() => setCleanupKind(null)}
      />

      <Dialog
        open={footprintInfoOpen}
        title={t("rework.home.responsible.footprintInfo.title")}
        confirmLabel={t("rework.home.responsible.footprintInfo.confirm")}
        hideCancel
        onConfirm={() => setFootprintInfoOpen(false)}
        onCancel={() => setFootprintInfoOpen(false)}
      >
        <div className={styles.infoBody}>
          <p>{t("rework.home.responsible.footprintInfo.how")}</p>
          <p>{t("rework.home.responsible.footprintInfo.convert")}</p>
          <p className={styles.infoSubhead}>{t("rework.home.responsible.footprintInfo.limitsTitle")}</p>
          <ul className={styles.infoList}>
            <li>{t("rework.home.responsible.footprintInfo.limit1")}</li>
            <li>{t("rework.home.responsible.footprintInfo.limit2")}</li>
            <li>{t("rework.home.responsible.footprintInfo.limit3")}</li>
          </ul>
        </div>
      </Dialog>
    </section>
  );
}
