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
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { IconType } from "@shared/utils/Type.ts";
import type { HomePeriod } from "../HomePage.tsx";
import CleanupDialog, { type CleanupGroup } from "../CleanupDialog/CleanupDialog.tsx";
import styles from "./ResponsibleAiSection.module.scss";

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
//
// SCOPE — the "files" indicator counts the caller's PERSONAL space only
// (personal-<uid>): it is their own storage, freely deletable. Team files are
// deliberately excluded — they are shared, "unused" there is a collective (not
// personal) notion, and deletion is permission-gated. (Conversations, by
// contrast, span the personal space AND every team the user belongs to.)
const INDICATORS_BY_PERIOD: Record<HomePeriod, Indicator[]> = {
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
    { tone: "info", icon: "show_chart", value: "280 k tokens", caption: "consommés sur les 7 derniers jours" },
    {
      tone: "eco",
      icon: "cloud",
      value: "≈ 26 g CO₂e · 0,2 kWh",
      caption: "empreinte estimée de vos échanges",
      info: true,
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
    { tone: "info", icon: "show_chart", value: "1,2 M tokens", caption: "consommés sur les 30 derniers jours" },
    {
      tone: "eco",
      icon: "cloud",
      value: "≈ 110 g CO₂e · 0,9 kWh",
      caption: "empreinte estimée de vos échanges",
      info: true,
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
    { tone: "info", icon: "show_chart", value: "3,4 M tokens", caption: "consommés sur les 90 derniers jours" },
    {
      tone: "eco",
      icon: "cloud",
      value: "≈ 320 g CO₂e · 2,6 kWh",
      caption: "empreinte estimée de vos échanges",
      info: true,
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
  const indicators = INDICATORS_BY_PERIOD[period];

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
            <div key={ind.value} className={styles.ind}>
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
