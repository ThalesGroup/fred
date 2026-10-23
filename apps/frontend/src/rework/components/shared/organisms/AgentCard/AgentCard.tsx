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
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { OptionModel } from "@models/Option.model.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import {
  ManagedAgentInstanceSummary,
  UserSummary,
} from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi.ts";
import styles from "./AgentCard.module.scss";
import TeamMarketplaceState from "./TeamMarketplaceState.tsx";

type MoreMenuAction = "edit" | "toggle" | "duplicate" | "copyTo" | "publish" | "unpublish" | "delete";

/** What the viewer may do with this agent on the marketplace, decided by the page. */
export interface AgentCardMarketplace {
  /** The team can publish (switch on, public team): every card of the page shows the bar. */
  showBar: boolean;
  /** Editors only, never in the personal space; greyed with the reason as tooltip. */
  publishAction?: { kind: "publish" | "republish"; disabledReason?: string };
  /** Editors and the team admin, while the agent is published. */
  canRemove: boolean;
  /** Editors and the team admin see Modified and Removed. */
  showDetailedState: boolean;
  canHide: boolean;
  onPublish: () => void;
  onRemove: () => void;
  onHide: () => void;
}

export interface AgentCardProps {
  instance: ManagedAgentInstanceSummary;
  templateDisplayName?: string;
  runtimeId?: string;
  /** Needed to build the managed-chat route for the Chat button. */
  teamId?: string;
  canManageAgents: boolean;
  offline?: boolean;
  /** Resolved audit users for `created_by`/`updated_by`, batched once for the
   *  whole list by the caller rather than one query per card. */
  auditUserById?: Map<string, UserSummary>;
  onEdit: () => void;
  onToggleEnabled: () => void;
  onDuplicate: () => void;
  onCopyTo: () => void;
  onDelete: () => void;
  marketplace?: AgentCardMarketplace;
}

function formatShortDate(dateStr: string | null | undefined): string | undefined {
  if (!dateStr) return undefined;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return undefined;
  const datePart = date.toLocaleDateString();
  // Fixed 24h "HH:MM" (zero-padded), independent of locale — toLocaleTimeString's
  // padding/12h-vs-24h choice varies by browser and locale.
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${datePart} - ${hours}:${minutes}`;
}

export default function AgentCard({
  instance,
  templateDisplayName,
  runtimeId,
  teamId,
  canManageAgents,
  offline = false,
  auditUserById,
  onEdit,
  onToggleEnabled,
  onDuplicate,
  onCopyTo,
  onDelete,
  marketplace,
}: AgentCardProps) {
  const { agentIconName } = useFrontendProperties();
  const { t } = useTranslation();
  // A suspended instance (#1975, RFC §3.9) is a platform-forced broken state
  // distinct from the editor's enable toggle: it never counts as enabled (no
  // chat affordance) and its enable toggle is LOCKED — the fix is in settings.
  const isSuspended = !!instance.suspension_reason;
  const isEnabled = !offline && !isSuspended && instance.status === "enabled";
  const toggleLabel = isSuspended
    ? t("rework.agentCard.suspendedToggleLocked")
    : isEnabled
      ? t("rework.agentCard.deactivate")
      : t("rework.agentCard.activate");
  // Best-effort keyword guess from the agent's own identity, falling back to
  // the site's configured default icon when nothing matches (#2076 follow-up).
  const iconName = resolveAgentIcon(instance, agentIconName);

  const createdByName = instance.created_by
    ? userDisplayName(instance.created_by, auditUserById?.get(instance.created_by))
    : undefined;
  const updatedByName = instance.updated_by
    ? userDisplayName(instance.updated_by, auditUserById?.get(instance.updated_by))
    : undefined;
  const createdAt = formatShortDate(instance.created_at);
  const updatedAt = formatShortDate(instance.updated_at);

  const infoTooltipContent = (
    <div className={styles.infoTooltip}>
      {runtimeId && (
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t("rework.agentCard.tooltip.origin")}</span>
          <span className={styles.infoValue}>{runtimeId}</span>
        </div>
      )}
      {templateDisplayName && (
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t("rework.agentCard.tooltip.template")}</span>
          <span className={styles.infoValue}>{templateDisplayName}</span>
        </div>
      )}
      {createdByName && (
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t("rework.agentCard.tooltip.created")}</span>
          <span className={styles.infoValueStacked}>
            <span>{createdByName}</span>
            {createdAt && <span className={styles.infoValueDate}>{createdAt}</span>}
          </span>
        </div>
      )}
      {updatedByName && (
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t("rework.agentCard.tooltip.updated")}</span>
          <span className={styles.infoValueStacked}>
            <span>{updatedByName}</span>
            {updatedAt && <span className={styles.infoValueDate}>{updatedAt}</span>}
          </span>
        </div>
      )}
    </div>
  );

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

  const handleMoreMenuSelect = (action: MoreMenuAction) => {
    if (action === "edit") onEdit();
    else if (action === "toggle") {
      if (isSuspended) return;
      onToggleEnabled();
    } else if (action === "duplicate") onDuplicate();
    else if (action === "copyTo") onCopyTo();
    else if (action === "publish") marketplace?.onPublish();
    else if (action === "unpublish") marketplace?.onRemove();
    else if (action === "delete") onDelete();
  };

  // A team admin who is not an editor still gets the menu, with Remove only.
  const menuOptions: OptionModel<MoreMenuAction>[] = [];
  if (canManageAgents) {
    menuOptions.push(
      {
        key: "edit",
        value: "edit",
        label: t("rework.agentCard.edit"),
        icon: { category: "outlined", type: "edit" },
      },
      {
        key: "toggle",
        value: "toggle",
        label: toggleLabel,
        icon: { category: "outlined", type: isEnabled ? "visibility_off" : "visibility" },
        disabled: isSuspended,
      },
      {
        key: "duplicate",
        value: "duplicate",
        label: t("rework.agentCard.duplicate"),
        icon: { category: "outlined", type: "content_copy" },
      },
      {
        key: "copyTo",
        value: "copyTo",
        label: t("rework.agentCard.copyTo"),
        icon: { category: "outlined", type: "drive_file_move" },
      },
    );
  }
  if (marketplace?.publishAction) {
    const { kind, disabledReason } = marketplace.publishAction;
    menuOptions.push({
      key: "publish",
      value: "publish",
      label: t(
        kind === "republish" ? "rework.agentMarketplace.menu.republish" : "rework.agentMarketplace.menu.publish",
      ),
      icon: { category: "outlined", type: "storefront" },
      disabled: Boolean(disabledReason),
      tooltip: disabledReason,
    });
  }
  if (marketplace?.canRemove) {
    menuOptions.push({
      key: "unpublish",
      value: "unpublish",
      label: t("rework.agentMarketplace.menu.remove"),
      icon: { category: "outlined", type: "do_not_disturb_on" },
    });
  }
  if (canManageAgents) {
    menuOptions.push({
      key: "delete",
      value: "delete",
      label: t("rework.agentCard.delete"),
      icon: { category: "outlined", type: "delete" },
      destructive: true,
    });
  }

  return (
    <div className={styles.agentCard} data-enabled={isEnabled}>
      <div className={styles.agentInfo}>
        <div className={styles.agentPresentation}>
          <div className={styles.agentIcon}>
            <Icon category={"outlined"} type={iconName} />
          </div>
          <div className={styles.agentIdentity}>
            <div className={styles.agentName}>{instance.display_name}</div>
            <div className={styles.agentRole}>{instance.role}</div>
          </div>
          {menuOptions.length > 0 && (
            <div className={styles.moreMenu}>
              <IconButtonMenu<MoreMenuAction>
                iconButton={{
                  color: "on-surface-retreat",
                  variant: "icon",
                  size: "medium",
                  iconSize: "small",
                  icon: { category: "outlined", type: "more_vert" },
                  "aria-label": t("rework.agentCard.moreMenu"),
                }}
                options={menuOptions}
                onSelect={handleMoreMenuSelect}
              />
            </div>
          )}
        </div>
        <div className={styles.agentDescription}>{instance.description || t("rework.agentCard.noDescription")}</div>
      </div>

      {!isSuspended && instance.catalog_warnings && instance.catalog_warnings.length > 0 && (
        <div className={styles.catalogWarning}>{t("rework.agentCard.catalogWarning")}</div>
      )}

      <div className={styles.footer}>
        {isSuspended && <div className={styles.suspensionWarning}>{t("rework.agentCard.suspended")}</div>}
        <div className={styles.actions}>
          <Tooltip content={infoTooltipContent}>
            <span className={styles.infoIcon} tabIndex={0}>
              <Icon category="outlined" type="info" accessibleName={t("rework.agentCard.tooltip.label")} />
            </span>
          </Tooltip>
          {isEnabled && teamId ? (
            <Link to={`/team/${teamId}/managed-chat/${instance.agent_instance_id}`} className={styles.chatLink}>
              {chatButton}
            </Link>
          ) : (
            chatButton
          )}
        </div>
      </div>

      {marketplace?.showBar && (
        <TeamMarketplaceState
          marketplace={instance.marketplace}
          showDetailedState={marketplace.showDetailedState}
          canHide={marketplace.canHide}
          onHide={marketplace.onHide}
        />
      )}
    </div>
  );
}
