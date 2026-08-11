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
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import {
  useBulkDeleteMySessionsMutation,
  useMyInactiveSessionsQuery,
  useUserTokenUsageOverTimeQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import type { HomePeriod } from "../HomePage.tsx";
import { homePeriodRange } from "../homePeriod.ts";
import CleanupDialog, { type CleanupGroup, type CleanupItem } from "../CleanupDialog/CleanupDialog.tsx";
import styles from "./ResponsibleAiSection.module.scss";

const nf = (maximumFractionDigits: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits });

// A conversation counts as inactive after this many days without activity.
const INACTIVE_DAYS = 5;

type IndicatorTone = "warn" | "info" | "eco";
type CleanupKind = "conversations";

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

  // LIVE — the green-cost estimate of the user's token usage over the period.
  // The `user_token_usage_over_time` preset already derives co2e/kwh per bucket
  // server-side (the raw token total itself now lives in the activity row).
  // Memoise the range on `period`: a fresh `until` every render would change the
  // cache key and refetch in a loop. TTL 300s (KPI-ANALYTICS-RFC.md §2.6).
  const range = useMemo(() => homePeriodRange(period), [period]);
  const {
    data: usageData,
    isLoading: usageLoading,
    isError: usageError,
  } = useUserTokenUsageOverTimeQuery(range, { refetchOnMountOrArgChange: 300 });

  const footprint = useMemo(() => {
    const rows = usageData?.rows ?? [];
    return {
      co2e: rows.reduce((acc, r) => acc + (r.co2e_grams ?? 0), 0),
      kwh: rows.reduce((acc, r) => acc + (r.kwh ?? 0), 0),
    };
  }, [usageData]);

  // "…" while the first fetch resolves, "—" if the KPI service is unavailable
  // (OpenSearch down → 503); otherwise the real aggregate.
  const footprintValue = usageLoading
    ? "…"
    : usageError
      ? "—"
      : `≈ ${nf(1).format(footprint.co2e)} g CO₂e · ${nf(2).format(footprint.kwh)} kWh`;

  // LIVE — the caller's inactive conversations across every space. Deliberately
  // NOT period-scoped (unlike the tiles above): a cleanup tool should surface
  // every stale conversation, however old, so the user can clear as much as
  // possible. The count feeds the tile; the same rows, grouped by space, feed
  // the cleanup dialog. team_id → display name comes from bootstrap.
  const { availableTeams } = useFrontendBootstrap();
  const teamNameById = useMemo(() => new Map(availableTeams.map((tm) => [tm.id, tm.name])), [availableTeams]);
  const {
    data: inactiveData,
    isLoading: inactiveLoading,
    isError: inactiveError,
  } = useMyInactiveSessionsQuery({ inactiveDays: INACTIVE_DAYS }, { refetchOnMountOrArgChange: 300 });
  const [bulkDeleteSessions] = useBulkDeleteMySessionsMutation();

  const { conversationGroups, teamIdBySession } = useMemo(() => {
    const sessions = inactiveData?.sessions ?? [];
    const label = (teamId: string) =>
      isPersonalTeamId(teamId) ? t("rework.home.topTeams.personalSpace") : (teamNameById.get(teamId) ?? teamId);
    const itemsByTeam = new Map<string, CleanupItem[]>();
    const teamBySession = new Map<string, string>();
    for (const s of sessions) {
      teamBySession.set(s.session_id, s.team_id);
      const items = itemsByTeam.get(s.team_id) ?? [];
      items.push({ id: s.session_id, title: s.title || "Conversation sans titre", meta: s.agent_name ?? undefined });
      itemsByTeam.set(s.team_id, items);
    }
    // Personal space first, then teams alphabetically.
    const groups: CleanupGroup[] = [...itemsByTeam.entries()]
      .sort(
        ([a], [b]) => Number(!isPersonalTeamId(a)) - Number(!isPersonalTeamId(b)) || label(a).localeCompare(label(b)),
      )
      .map(([teamId, items]) => ({ key: teamId, label: label(teamId), items }));
    return { conversationGroups: groups, teamIdBySession: teamBySession };
  }, [inactiveData, teamNameById, t]);

  const conversationsCount = inactiveData?.sessions.length ?? 0;
  const conversationsValue = inactiveLoading
    ? "…"
    : inactiveError
      ? "—"
      : `${conversationsCount} conversation${conversationsCount > 1 ? "s" : ""} inactive${conversationsCount > 1 ? "s" : ""}`;

  const indicators: Indicator[] = [
    {
      tone: "warn",
      icon: "forum",
      value: conversationsValue,
      caption: "depuis plus de 5 jours",
      cleanupKind: "conversations",
    },
    { tone: "eco", icon: "cloud", value: footprintValue, caption: "empreinte estimée de vos échanges", info: true },
  ];

  const handleCleanupConfirm = async (ids: string[]) => {
    setCleanupKind(null);
    const sessions = ids
      .map((id) => ({ session_id: id, team_id: teamIdBySession.get(id) }))
      .filter((ref): ref is { session_id: string; team_id: string } => Boolean(ref.team_id));
    try {
      const res = await bulkDeleteSessions({ bulkDeleteSessionsRequest: { sessions } }).unwrap();
      showSuccess({ summary: t("rework.home.responsible.cleanupTool.toast", { count: res.deleted.length }) });
    } catch {
      // The list is left intact; the tag invalidation keeps it truthful.
    }
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
        title={t("rework.home.responsible.cleanupConversations.title")}
        subtitle={t("rework.home.responsible.cleanupConversations.subtitle")}
        groups={conversationGroups}
        emptyLabel={t("rework.home.responsible.cleanupConversations.empty")}
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
