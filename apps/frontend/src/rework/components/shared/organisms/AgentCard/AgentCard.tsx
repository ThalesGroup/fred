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
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { materialIcons, type MaterialIconType } from "@shared/utils/Type.ts";
import { guessAgentIcon } from "@shared/utils/agentIcon.ts";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./AgentCard.module.scss";

export interface AgentCardProps {
  instance: ManagedAgentInstanceSummary;
  templateDisplayName?: string;
  runtimeId?: string;
  /** Needed to build the managed-chat route for the Chat button. */
  teamId?: string;
  canManageAgents: boolean;
  offline?: boolean;
  onEdit: () => void;
  onToggleEnabled: () => void;
}

export default function AgentCard({
  instance,
  templateDisplayName,
  runtimeId,
  teamId,
  canManageAgents,
  offline = false,
  onEdit,
  onToggleEnabled,
}: AgentCardProps) {
  const { agentIconName } = useFrontendProperties();
  const { t } = useTranslation();
  // A suspended instance (#1975, RFC §3.9) is a platform-forced broken state
  // distinct from the editor's enable toggle: it never counts as enabled (no
  // chat affordance) and its enable toggle is LOCKED — the fix is in settings.
  const isSuspended = !!instance.suspension_reason;
  const isEnabled = !offline && !isSuspended && instance.status === "enabled";
  const toggleTooltip = isSuspended
    ? t("rework.agentCard.suspendedToggleLocked")
    : isEnabled
      ? t("rework.agentCard.deactivate")
      : t("rework.agentCard.activate");
  // Best-effort keyword guess from the agent's own identity, falling back to
  // the site's configured default icon when nothing matches (#2076 follow-up).
  // `agentIconName` is an untyped site-config string; guessAgentIcon's
  // fallback must be a real MaterialIconType, so it's validated the same way
  // `toIconType` does, narrowed to the material (non-custom) subset.
  const defaultIcon: MaterialIconType = (materialIcons as readonly string[]).includes(agentIconName)
    ? (agentIconName as MaterialIconType)
    : "smart_toy";
  const iconName = guessAgentIcon(instance.display_name, instance.role, instance.description ?? "", defaultIcon);
  // Raw source_runtime_id, not a prettified label (e.g. "fred-agents"), per
  // the agent card redesign (#2076).
  const origin = [runtimeId, templateDisplayName].filter(Boolean).join(" · ");

  const chatButton = (
    <Button
      color="primary"
      variant="outlined"
      size="medium"
      icon={{ category: "outlined", type: "reviews" }}
      className={styles.chatButton}
      disabled={!isEnabled}
    >
      {t("rework.agentCard.chat")}
    </Button>
  );

  return (
    <div className={styles.agentCard} data-enabled={isEnabled}>
      <div className={styles.agentInfo}>
        <div className={styles.agentPresentation}>
          <div className={styles.agentIcon}>
            <Icon category={"outlined"} type={iconName} />
          </div>
          <div className={styles.agentIdentity}>
            {origin && <div className={styles.agentOrigin}>{origin}</div>}
            <div className={styles.agentName}>{instance.display_name}</div>
            <div className={styles.agentRole}>{instance.role}</div>
          </div>
        </div>
        <div className={styles.agentDescription}>{instance.description || t("rework.agentCard.noDescription")}</div>
      </div>

      {isSuspended ? (
        <div className={styles.suspensionWarning}>{t("rework.agentCard.suspended")}</div>
      ) : (
        instance.catalog_warnings &&
        instance.catalog_warnings.length > 0 && (
          <div className={styles.catalogWarning}>{t("rework.agentCard.catalogWarning")}</div>
        )
      )}

      <div className={styles.actions}>
        {canManageAgents && (
          <div className={styles.actionsLeft}>
            <Tooltip text={toggleTooltip}>
              <IconButton
                color="on-surface"
                variant="icon"
                size="medium"
                // A suspended instance has a LOCKED enable toggle (#1975, RFC §3.9):
                // the fix is in the edit form, not a re-enable. Disable it so an
                // editor cannot toggle a broken agent back into the catalog.
                disabled={isSuspended}
                icon={{ category: "outlined", type: isEnabled ? "visibility" : "visibility_off" }}
                onClick={() => {
                  if (isSuspended) return;
                  onToggleEnabled();
                }}
              />
            </Tooltip>
            <Tooltip text={t("rework.agentCard.edit")}>
              <IconButton
                color="on-surface"
                variant="icon"
                size="medium"
                icon={{ category: "outlined", type: "edit" }}
                onClick={onEdit}
              />
            </Tooltip>
          </div>
        )}
        {isEnabled && teamId ? (
          <Link to={`/team/${teamId}/managed-chat/${instance.agent_instance_id}`} className={styles.chatLink}>
            {chatButton}
          </Link>
        ) : (
          chatButton
        )}
      </div>
    </div>
  );
}
