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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import {
  useLazyTeamAgentInstancesQuery,
  useUserRecentAgentsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import CompactAgentCard from "./CompactAgentCard.tsx";
import styles from "./RecentAgents.module.scss";

const TILE_COUNT = 5;

/** Home page — the agents the current user interacted with most recently
 * (live: self-scoped `user_recent_agents` preset, newest first). The preset
 * returns only ids/names, so each row is resolved to its full agent instance
 * (needed for the derived icon + role) via the per-team instances query; the
 * preset over-fetches so we can drop agents that are gone/disabled/access-lost
 * and still fill 5 tiles. Period-independent by design — the section ignores
 * the page's period selector and asks for a wide window. Hidden entirely when
 * nothing resolves. */
export default function RecentAgents() {
  const { t } = useTranslation();
  const { availableTeams } = useFrontendBootstrap();

  // team_id → display name (personal space shown as "Espace personnel"), for the
  // origin label on each tile. Same mapping as the leaderboard cards.
  const teamNameById = useMemo(() => new Map(availableTeams.map((team) => [team.id, team.name])), [availableTeams]);
  const teamLabel = (teamId: string): string | undefined =>
    isPersonalTeamId(teamId) ? t("rework.home.topTeams.personalSpace") : teamNameById.get(teamId);

  // Wide, fixed window captured once on mount — "recently used" is not tied to
  // the page's period selector. Memoised so `until` doesn't change every render
  // (which would rotate the RTK Query cache key and refetch in a loop).
  const range = useMemo(() => {
    const until = new Date();
    const since = new Date(until.getTime() - 365 * 24 * 60 * 60 * 1000);
    return { since: since.toISOString(), until: until.toISOString() };
  }, []);
  const { data } = useUserRecentAgentsQuery(range, { refetchOnMountOrArgChange: 300 });
  const rows = useMemo(() => data?.rows ?? [], [data]);

  // Resolve the ids to full instances, one cached fetch per distinct origin
  // team (the recent list spans a variable set of teams, so a fixed number of
  // query hooks won't do — hence the lazy trigger accumulated into state).
  const [fetchInstances] = useLazyTeamAgentInstancesQuery();
  const [instancesByTeam, setInstancesByTeam] = useState<Record<string, ManagedAgentInstanceSummary[]>>({});

  const teamIds = useMemo(() => {
    const ids = new Set<string>();
    for (const row of rows) if (row.team_id) ids.add(row.team_id);
    return [...ids];
  }, [rows]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all(
      teamIds.map(async (teamId) => {
        try {
          // preferCacheValue: reuse a warm cache (e.g. from TeamAgentsPage)
          // rather than refetch.
          const list = await fetchInstances({ teamId }, true).unwrap();
          return [teamId, list] as const;
        } catch {
          return [teamId, [] as ManagedAgentInstanceSummary[]] as const;
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      setInstancesByTeam((prev) => {
        const next = { ...prev };
        for (const [teamId, list] of entries) next[teamId] = list;
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [teamIds, fetchInstances]);

  const tiles = useMemo(() => {
    const out: { instance: ManagedAgentInstanceSummary; teamId: string }[] = [];
    for (const row of rows) {
      if (!row.team_id) continue;
      const list = instancesByTeam[row.team_id];
      if (!list) continue; // team not resolved yet
      const instance = list.find((i) => i.agent_instance_id === row.agent_instance_id);
      // Skip agents that no longer exist / the user can't reach, and disabled or
      // suspended ones — a launcher tile should always be usable.
      if (!instance || instance.status !== "enabled" || instance.suspension_reason) continue;
      out.push({ instance, teamId: row.team_id });
      if (out.length >= TILE_COUNT) break;
    }
    return out;
  }, [rows, instancesByTeam]);

  if (tiles.length === 0) return null;

  return (
    <section className={styles.section} aria-label={t("rework.home.recentAgents.title")}>
      <div className={styles.head}>
        <Icon category="outlined" type="history" />
        <h2 className={styles.title}>{t("rework.home.recentAgents.title")}</h2>
      </div>
      <div className={styles.row} data-count={tiles.length}>
        {tiles.map(({ instance, teamId }) => (
          <CompactAgentCard
            key={instance.agent_instance_id}
            instance={instance}
            teamId={teamId}
            teamName={teamLabel(teamId)}
          />
        ))}
      </div>
    </section>
  );
}
