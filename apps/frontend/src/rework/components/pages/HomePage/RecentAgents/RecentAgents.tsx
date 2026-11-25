// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import AgentCard from "@shared/organisms/AgentCard/AgentCard";
import type { HomeAgent } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import CompactAgentCard from "./CompactAgentCard";
import SectionMarker from "../SectionMarker/SectionMarker";
import styles from "./RecentAgents.module.scss";

const noop = () => undefined;

/** Server-filtered launchers: retained conversations first, then accessible suggestions. */
export default function RecentAgents({
  agents = [],
  variant = "compact",
}: {
  agents?: HomeAgent[];
  variant?: "compact" | "detailed";
}) {
  const { t } = useTranslation();
  if (!agents.length) return null;
  const title = t("rework.home.recentAgents.suggestedTitle");
  return (
    <section className={styles.section} data-variant={variant} aria-label={title}>
      <div className={styles.head}>
        {variant === "detailed" ? <SectionMarker /> : <Icon category="outlined" type="history" />}
        <h2 className={styles.title}>{title}</h2>
      </div>
      <div className={variant === "detailed" ? styles.grid : styles.row} data-count={agents.length}>
        {agents.map((agent) => {
          // Presentation adapter for the existing card. The server only returns enabled, ready agents.
          const instance = { ...agent, team_id: agent.space_id, status: "enabled" as const };
          return variant === "detailed" ? (
            <AgentCard
              key={agent.agent_instance_id}
              instance={instance}
              teamId={agent.space_id}
              canManageAgents={false}
              onEdit={noop}
              onToggleEnabled={noop}
              onDuplicate={noop}
              onCopyTo={noop}
              onDelete={noop}
            />
          ) : (
            <CompactAgentCard
              key={agent.agent_instance_id}
              instance={instance}
              teamId={agent.space_id}
              teamName={agent.space_name}
            />
          );
        })}
      </div>
    </section>
  );
}
