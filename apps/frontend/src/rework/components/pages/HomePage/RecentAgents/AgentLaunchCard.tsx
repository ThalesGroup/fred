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
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./AgentLaunchCard.module.scss";

interface AgentLaunchCardProps {
  instance: ManagedAgentInstanceSummary;
  /** Origin team name, or the personal-space label. */
  teamName?: string;
}

/** Advanced-home card: who the agent is and what it does, with one chat button. */
export default function AgentLaunchCard({ instance, teamName }: AgentLaunchCardProps) {
  const { t } = useTranslation();
  const { agentIconName } = useFrontendProperties();

  return (
    <article className={styles.card}>
      <div className={styles.identity}>
        <span className={styles.icon}>
          <Icon category="outlined" type={resolveAgentIcon(instance, agentIconName)} />
        </span>
        <div className={styles.names}>
          {teamName && <span className={styles.team}>{teamName}</span>}
          <h3 className={styles.name}>{instance.display_name}</h3>
        </div>
      </div>
      <p className={styles.pitch}>{instance.role}</p>
      {instance.description && <p className={styles.description}>{instance.description}</p>}
      <Link
        to={`/team/${instance.team_id}/managed-chat/${instance.agent_instance_id}`}
        className={styles.launch}
        aria-label={t("rework.home.advanced.chatWith", { name: instance.display_name })}
      >
        <Icon category="outlined" type="chat_bubble" />
        {t("rework.home.advanced.chat")}
      </Link>
    </article>
  );
}
