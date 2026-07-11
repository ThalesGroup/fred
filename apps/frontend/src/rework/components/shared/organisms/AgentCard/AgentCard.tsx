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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./AgentCard.module.scss";

export interface AgentCardProps {
  instance: ManagedAgentInstanceSummary;
  templateDisplayName?: string;
  templateCategory?: string;
  runtimeId?: string;
  canManageAgents: boolean;
  offline?: boolean;
  onEdit: () => void;
  onToggleEnabled: () => void;
}

export default function AgentCard({
  instance,
  templateDisplayName,
  templateCategory,
  runtimeId,
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
                {templateCategory && <span className={styles.agentCategory}>{templateCategory}</span>}
                {templateDisplayName && <span className={styles.agentTemplate}>{templateDisplayName}</span>}
                {runtimeId && <span className={styles.agentPod}>{runtimeId}</span>}
              </div>
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

        {canManageAgents && (
          <div className={styles.actions}>
            <IconButton
              color="on-surface"
              variant="icon"
              size="medium"
              // A suspended instance has a LOCKED enable toggle (#1975, RFC §3.9):
              // the fix is in the edit form, not a re-enable. Disable it so an
              // editor cannot toggle a broken agent back into the catalog.
              disabled={isSuspended}
              title={isSuspended ? t("rework.agentCard.suspendedToggleLocked") : undefined}
              icon={{ category: "outlined", type: isEnabled ? "visibility" : "visibility_off" }}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (isSuspended) return;
                onToggleEnabled();
              }}
            />
            <IconButton
              color="on-surface"
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "edit" }}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onEdit();
              }}
            />
          </div>
        )}
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
