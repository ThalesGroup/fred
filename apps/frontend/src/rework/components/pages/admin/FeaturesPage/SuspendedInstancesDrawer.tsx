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

// Health-column drill-down: the agents behind a "N suspended" count, grouped
// by space. Read-only; callers supply the title and the instance list.

import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import styles from "./SuspendedInstancesDrawer.module.css";

export interface SuspendedInstance {
  spaceId: string;
  spaceName: string;
  displayName: string;
}

interface SuspendedInstancesDrawerProps {
  title: string;
  instances: SuspendedInstance[];
  open: boolean;
  onClose: () => void;
}

interface SpaceGroup {
  spaceId: string;
  spaceName: string;
  agents: string[];
}

export function SuspendedInstancesDrawer({ title, instances, open, onClose }: SuspendedInstancesDrawerProps) {
  const { t } = useTranslation();

  // Keyed by id so same-named spaces stay apart; sorted by name for a stable order.
  const groups = useMemo<SpaceGroup[]>(() => {
    const bySpace = new Map<string, SpaceGroup>();
    for (const instance of instances) {
      const group = bySpace.get(instance.spaceId);
      if (group) {
        group.agents.push(instance.displayName);
      } else {
        bySpace.set(instance.spaceId, {
          spaceId: instance.spaceId,
          spaceName: instance.spaceName,
          agents: [instance.displayName],
        });
      }
    }
    const ordered = [...bySpace.values()];
    ordered.sort((a, b) => a.spaceName.localeCompare(b.spaceName));
    for (const group of ordered) group.agents.sort((a, b) => a.localeCompare(b));
    return ordered;
  }, [instances]);

  return (
    <InlineDrawer open={open} onClose={onClose} title={title} width="440px">
      {open && (
        <div className={styles.body}>
          <p className={styles.hint}>{t("rework.admin.capabilities.suspendedDrawer.subtitle")}</p>
          <ul className={styles.teamList}>
            {groups.map((group) => (
              <li key={group.spaceId} className={styles.teamGroup}>
                <div className={styles.teamHeader}>
                  <span className={styles.teamName} title={group.spaceName}>
                    {group.spaceName}
                  </span>
                  <span className={styles.teamCount}>
                    {t("rework.admin.capabilities.suspendedDrawer.teamCount", { count: group.agents.length })}
                  </span>
                </div>
                <ul className={styles.agentList}>
                  {group.agents.map((name, index) => (
                    <li key={`${group.spaceId}-${index}`} className={styles.agentItem} title={name}>
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
