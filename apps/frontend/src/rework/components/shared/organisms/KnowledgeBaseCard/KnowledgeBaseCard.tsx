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
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { splitDuration } from "@shared/molecules/ScheduleField/ScheduleField.tsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { KnowledgeBaseInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
// Share the agent card layout; document navigation uses the standard Button
// appearance rather than the animated conversation action.
import styles from "../AgentCard/AgentCard.module.scss";

type MoreMenuAction = "edit" | "delete";

export interface KnowledgeBaseCardProps {
  instance: KnowledgeBaseInstanceSummary;
  teamId: string;
  /** What its source declares it does, resolved once for the whole list by the
   *  caller rather than one query per card. */
  definitionDescription?: string;
  /** Withholds the row menu. Deleting a base takes its documents with it. */
  canManage: boolean;
  onEdit: () => void;
  onDelete: () => void;
}

function formatShortDate(dateStr: string | null | undefined): string | undefined {
  if (!dateStr) return undefined;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toLocaleDateString();
}

export default function KnowledgeBaseCard({
  instance,
  teamId,
  definitionDescription,
  canManage,
  onEdit,
  onDelete,
}: KnowledgeBaseCardProps) {
  const { t } = useTranslation();
  const createdAt = formatShortDate(instance.created_at);
  // Read back in the unit a user would have typed, not in seconds.
  const { every, unit } = splitDuration(instance.schedule.every_seconds);

  const handleMoreMenuSelect = (action: MoreMenuAction) => {
    if (action === "edit") onEdit();
    else if (action === "delete") onDelete();
  };

  const infoTooltipContent = (
    <div className={styles.infoTooltip}>
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>{t("rework.knowledgeBases.card.tooltip.kind")}</span>
        <span className={styles.infoValue}>{instance.definition_name}</span>
      </div>
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>{t("rework.knowledgeBases.card.tooltip.cadence")}</span>
        <span className={styles.infoValue}>{`${every} ${t(`rework.schedule.unit.${unit}`)}`}</span>
      </div>
      {createdAt && (
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t("rework.knowledgeBases.card.tooltip.created")}</span>
          <span className={styles.infoValue}>{createdAt}</span>
        </div>
      )}
    </div>
  );

  return (
    <div className={styles.agentCard} data-enabled={!instance.suspended}>
      <div className={styles.agentInfo}>
        <div className={styles.agentPresentation}>
          <div className={styles.agentIcon}>
            <Icon category="outlined" type="database" />
          </div>
          <div className={styles.agentIdentity}>
            <div className={styles.agentName}>{instance.library_name}</div>
            <div className={styles.agentRole}>{instance.definition_name}</div>
          </div>
          {canManage && (
            <div className={styles.moreMenu}>
              <IconButtonMenu<MoreMenuAction>
                iconButton={{
                  color: "on-surface-retreat",
                  variant: "icon",
                  size: "medium",
                  icon: { category: "outlined", type: "more_vert" },
                }}
                options={[
                  {
                    key: "edit",
                    value: "edit",
                    label: t("rework.knowledgeBases.card.edit"),
                    icon: { category: "outlined", type: "edit" },
                  },
                  {
                    key: "delete",
                    value: "delete",
                    label: t("rework.knowledgeBases.card.delete"),
                    icon: { category: "outlined", type: "delete" },
                    destructive: true,
                  },
                ]}
                onSelect={handleMoreMenuSelect}
              />
            </div>
          )}
        </div>
        <div className={styles.agentDescription}>
          {definitionDescription || t("rework.knowledgeBases.card.noDescription")}
        </div>
      </div>

      {instance.suspended && (
        <div className={styles.suspensionWarning}>{t("rework.knowledgeBases.card.suspended")}</div>
      )}

      <div className={styles.actions}>
        <Tooltip content={infoTooltipContent}>
          <IconButton
            color="on-surface-retreat"
            variant="icon"
            size="medium"
            icon={{ category: "outlined", type: "info" }}
            aria-label={t("rework.knowledgeBases.card.tooltip.label")}
          />
        </Tooltip>
        <Link to={`/team/${teamId}/knowledge-bases/${instance.id}`} className={styles.chatLink}>
          <Button color="on-surface" variant="outlined" size="medium" icon={{ category: "outlined", type: "folder" }}>
            {t("rework.knowledgeBases.card.open")}
          </Button>
        </Link>
      </div>
    </div>
  );
}
