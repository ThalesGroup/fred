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

import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import AgentMarketplaceBar, {
  formatMarketplaceDate,
  MarketplaceCounter,
} from "@shared/molecules/AgentMarketplaceBar/AgentMarketplaceBar.tsx";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type { MarketplaceAgentSummary } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi.ts";
import styles from "./AgentCard.module.scss";

export interface MarketplaceAgentCardProps {
  agent: MarketplaceAgentSummary;
  /** True while a like or unlike of this card is in flight. */
  likePending?: boolean;
  onOpen: () => void;
  onToggleLike: () => void;
  onImport: () => void;
  /** Clicking the publishing team's name filters the page on that team. */
  onTeamClick?: () => void;
}

/** Marketplace variant of the agent card: same visual, no chat, toggle or more
 * menu; the bottom bar holds Like and Import. The author is the team only. */
export default function MarketplaceAgentCard({
  agent,
  likePending = false,
  onOpen,
  onToggleLike,
  onImport,
  onTeamClick,
}: MarketplaceAgentCardProps) {
  const { t, i18n } = useTranslation();
  const { agentIconName } = useFrontendProperties();
  const likes = agent.like_count ?? 0;
  const imports = agent.import_count ?? 0;
  const liked = !!agent.liked_by_me;

  return (
    <div className={styles.agentCard} data-enabled="true">
      {agent.team_name && (
        <div className={styles.agentTeam}>
          <span>
            {t("rework.marketplace.agents.card.byTeam")}{" "}
            {onTeamClick ? (
              <button
                type="button"
                className={styles.agentTeamLink}
                aria-label={t("rework.marketplace.agents.card.filterByTeam", { team: agent.team_name })}
                onClick={(event) => {
                  event.stopPropagation();
                  onTeamClick();
                }}
              >
                {agent.team_name}
              </button>
            ) : (
              agent.team_name
            )}
          </span>
        </div>
      )}
      <div className={styles.agentInfo}>
        <div className={styles.agentPresentation}>
          <div className={styles.agentIcon}>
            <Icon category="outlined" type={resolveAgentIcon(agent, agentIconName)} />
          </div>
          <div className={styles.agentIdentity}>
            <div className={styles.agentName}>{agent.display_name}</div>
            <div className={styles.agentRole}>{agent.role}</div>
          </div>
        </div>
        <div className={styles.agentDescription}>{agent.description || t("rework.agentCard.noDescription")}</div>
      </div>

      <div className={`${styles.actions} ${styles.marketplaceActions}`}>
        <Button
          color="primary"
          variant="outlined"
          size="medium"
          icon={{ category: "outlined", type: "visibility" }}
          className={styles.detailsButton}
          onClick={onOpen}
        >
          {t("rework.marketplace.agents.card.details")}
        </Button>
      </div>

      <AgentMarketplaceBar aria-label={t("rework.agentMarketplace.barLabel")} className={styles.marketplaceCardBar}>
        <span className={styles.marketplaceCardCounters}>
          <MarketplaceCounter
            icon="favorite"
            count={likes}
            pressed={liked}
            disabled={likePending}
            label={t("rework.marketplace.agents.card.like", { count: likes })}
            onClick={onToggleLike}
          />
          <MarketplaceCounter
            icon="download"
            count={imports}
            label={t("rework.marketplace.agents.card.import", { count: imports })}
            onClick={onImport}
          />
        </span>
        <span className={styles.marketplaceUpdated}>
          {t("rework.marketplace.agents.card.updatedOn", {
            date: formatMarketplaceDate(agent.published_at, i18n.language),
          })}
        </span>
      </AgentMarketplaceBar>
    </div>
  );
}
