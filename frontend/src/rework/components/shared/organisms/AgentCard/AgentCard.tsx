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
import { IconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./AgentCard.module.scss";

export interface AgentCardProps {
  instance: ManagedAgentInstanceSummary;
  templateDisplayName?: string;
  templateCategory?: string;
  canManageAgents: boolean;
  onEdit: () => void;
  onDelete: () => void;
}

/**
 * Displays one managed agent instance as a card.
 *
 * Enabled cards are wrapped by the caller in a <Link> to the managed chat
 * route. On hover the descriptive content blurs and a "Start Chat" overlay
 * appears — the gradient border animates during that state.
 *
 * Disabled cards render the same structure but without the hover effects and
 * with dimmed icon / muted text colors driven by the `data-enabled` cascade.
 *
 * Footer action buttons stay unblurred so they remain accessible on hover.
 */
export default function AgentCard({
  instance,
  templateDisplayName,
  templateCategory,
  canManageAgents,
  onEdit,
  onDelete,
}: AgentCardProps) {
  const { agentIconName } = useFrontendProperties();
  const { t } = useTranslation();
  const isEnabled = instance.status === "enabled";

  return (
    <div className={styles.agentCard} data-enabled={isEnabled}>
      <div className={styles.stateLayer}>
        <div className={styles.agentInfo}>
          <div className={styles.agentPresentation}>
            <div className={styles.agentIcon}>
              <Icon category={"outlined"} type={agentIconName as IconType} />
            </div>
            <div className={styles.agentIdentity}>
              <div className={styles.agentName}>{instance.display_name}</div>
              <div className={styles.agentMeta}>
                <span className={styles.agentStatus} data-status={instance.status}>
                  {instance.status}
                </span>
                {templateCategory && (
                  <span className={styles.agentCategory}>{templateCategory}</span>
                )}
              </div>
            </div>
          </div>
          <div className={styles.agentDescription}>
            {instance.description || t("rework.agentCard.noDescription", "No description yet.")}
          </div>
        </div>

        <div className={styles.footer}>
          {templateDisplayName && (
            <div className={styles.agentTemplate}>{templateDisplayName}</div>
          )}
          {canManageAgents && (
            <div className={styles.actions}>
              <Button
                color={"error"}
                variant={"text"}
                size={"medium"}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onDelete();
                }}
              >
                {t("common.delete")}
              </Button>
              <Button
                color={"on-surface"}
                variant={"text"}
                size={"medium"}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onEdit();
                }}
              >
                {t("rework.agentCard.settings", "Settings")}
              </Button>
            </div>
          )}
        </div>
      </div>

      {isEnabled && (
        <div className={styles.newChat}>
          <span className={styles.newChatIcon}>
            <Icon category={"outlined"} type={"reviews"} />
          </span>
          {t("rework.agentCard.startChat")}
        </div>
      )}
    </div>
  );
}
