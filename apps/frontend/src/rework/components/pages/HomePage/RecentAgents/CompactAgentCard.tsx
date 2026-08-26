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

import { Link } from "react-router-dom";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./CompactAgentCard.module.scss";

interface CompactAgentCardProps {
  instance: ManagedAgentInstanceSummary;
  teamId: string;
}

/** A stripped-down `AgentCard` for the Home "recently used agents" row: icon +
 * name + role, no more-menu / chat / info affordances. The whole tile is a
 * single link — clicking it enters the agent's team and opens a fresh
 * conversation (managed-chat with no `?session`, same target as AgentCard's
 * Chat button). Only ever rendered for enabled, resolvable agents, so it needs
 * no disabled/suspended state. */
export default function CompactAgentCard({ instance, teamId }: CompactAgentCardProps) {
  const { agentIconName } = useFrontendProperties();
  const iconName = resolveAgentIcon(instance, agentIconName);

  return (
    <Link to={`/team/${teamId}/managed-chat/${instance.agent_instance_id}`} className={styles.card}>
      <span className={styles.icon}>
        <Icon category="outlined" type={iconName} />
      </span>
      <span className={styles.identity}>
        <span className={styles.name}>{instance.display_name}</span>
        <span className={styles.role}>{instance.role}</span>
      </span>
    </Link>
  );
}
