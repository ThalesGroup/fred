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
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { KnowledgeBaseInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
// A Knowledge Base card and an agent card are the same object on screen: an
// icon, what it is called, what kind it is, a menu, an info bubble and one way
// in. Sharing the stylesheet is what keeps them identical — a copy would drift
// the first time either is touched.
import styles from "../AgentCard/AgentCard.module.scss";
import KnowledgeBaseConfiguration from "./KnowledgeBaseConfiguration.tsx";

type MoreMenuAction = "delete";

export interface KnowledgeBaseCardProps {
  instance: KnowledgeBaseInstanceSummary;
  teamId: string;
  /** Withholds the row menu. Deleting a base takes its documents with it. */
  canManage: boolean;
  onDelete: () => void;
}

function formatShortDate(dateStr: string | null | undefined): string | undefined {
  if (!dateStr) return undefined;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toLocaleDateString();
}

export default function KnowledgeBaseCard({ instance, teamId, canManage, onDelete }: KnowledgeBaseCardProps) {
  const { t } = useTranslation();
  const createdAt = formatShortDate(instance.created_at);

  const infoTooltipContent = (
    <div className={styles.infoTooltip}>
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>{t("rework.knowledgeBases.card.tooltip.kind")}</span>
        <span className={styles.infoValue}>{instance.definition_name}</span>
      </div>
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>{t("rework.knowledgeBases.card.tooltip.cadence")}</span>
        <span className={styles.infoValue}>{t(`rework.knowledgeBases.cadence.${instance.cadence}`)}</span>
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
                    key: "delete",
                    value: "delete",
                    label: t("rework.knowledgeBases.card.delete"),
                    icon: { category: "outlined", type: "delete" },
                    destructive: true,
                  },
                ]}
                onSelect={onDelete}
              />
            </div>
          )}
        </div>
        <div className={styles.agentDescription}>
          <KnowledgeBaseConfiguration
            definitionId={instance.definition_id}
            teamId={teamId}
            configuration={instance.configuration ?? {}}
          />
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
          <Button
            color="primary"
            variant="outlined"
            size="medium"
            icon={{ category: "outlined", type: "folder" }}
            className={styles.chatButton}
          >
            {t("rework.knowledgeBases.card.open")}
          </Button>
        </Link>
      </div>
    </div>
  );
}
