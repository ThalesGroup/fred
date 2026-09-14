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

// Health-column drill-down (CAPAB-01 / #1975): the agents behind a capability's
// resting "N suspended" count, grouped by team. Read-only — it names which
// agents, in which team, this capability breaks at rest, so an admin can go fix
// access team-by-team from the matrix drawer. The instance list comes inline on
// the aggregate item (`suspended_instance_details`), the same derivation as the
// count, so opening this needs no extra request.

import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { CapabilityEnablementItem, Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./SuspendedInstancesDrawer.module.css";

interface SuspendedInstancesDrawerProps {
  capability: CapabilityEnablementItem | null;
  teams: Team[];
  open: boolean;
  onClose: () => void;
}

interface TeamGroup {
  teamId: string;
  teamName: string;
  agents: string[];
}

export function SuspendedInstancesDrawer({ capability, teams, open, onClose }: SuspendedInstancesDrawerProps) {
  const { t } = useTranslation();

  // Group the flat instance list by team, resolving each opaque team id to its
  // name (ids are Keycloak group ids). Sorted by team name, agents by display
  // name, so the same catalog renders the same order every open. Memoised on the
  // capability identity — it changes when the list refetches, which is exactly
  // when the grouping must be recomputed.
  const groups = useMemo<TeamGroup[]>(() => {
    const details = capability?.suspended_instance_details ?? [];
    const teamName = (teamId: string) => teams.find((team) => team.id === teamId)?.name ?? teamId;
    const byTeam = new Map<string, TeamGroup>();
    for (const instance of details) {
      const group = byTeam.get(instance.team_id);
      if (group) {
        group.agents.push(instance.display_name);
      } else {
        byTeam.set(instance.team_id, {
          teamId: instance.team_id,
          teamName: teamName(instance.team_id),
          agents: [instance.display_name],
        });
      }
    }
    const ordered = [...byTeam.values()];
    ordered.sort((a, b) => a.teamName.localeCompare(b.teamName));
    for (const group of ordered) group.agents.sort((a, b) => a.localeCompare(b));
    return ordered;
  }, [capability, teams]);

  const title = capability
    ? t("rework.admin.capabilities.suspendedDrawer.title", {
        name: t(capability.name, { defaultValue: capability.name }),
      })
    : "";

  return (
    <InlineDrawer open={open} onClose={onClose} title={title} width="440px">
      {capability && (
        <div className={styles.body}>
          <p className={styles.hint}>{t("rework.admin.capabilities.suspendedDrawer.subtitle")}</p>
          <ul className={styles.teamList}>
            {groups.map((group) => (
              <li key={group.teamId} className={styles.teamGroup}>
                <div className={styles.teamHeader}>
                  <span className={styles.teamName} title={group.teamName}>
                    {group.teamName}
                  </span>
                  <span className={styles.teamCount}>
                    {t("rework.admin.capabilities.suspendedDrawer.teamCount", { count: group.agents.length })}
                  </span>
                </div>
                <ul className={styles.agentList}>
                  {group.agents.map((name, index) => (
                    <li key={`${group.teamId}-${index}`} className={styles.agentItem} title={name}>
                      {name}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
    </InlineDrawer>
  );
}
