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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import { formatMarketplaceDate } from "@shared/molecules/AgentMarketplaceBar/AgentMarketplaceBar.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import { PromptHighlight } from "@shared/molecules/PromptEditor/PromptEditor.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import {
  useMarketplaceAgentQuery,
  useUnpublishAgentMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  MarketplaceAgentDetail,
  MarketplaceAgentSummary,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { marketplaceErrorView } from "../../../TeamAgentsPage/agentMarketplace.ts";
import styles from "./MarketplaceAgentDialog.module.css";

const INSTRUCTIONS_FIELD = "prompts.system";
const REASON_MAX_LENGTH = 500;

interface MarketplaceAgentDialogProps {
  /** The listed agent; the dialog is open while it is set. */
  agent: MarketplaceAgentSummary | null;
  onImport: (agent: MarketplaceAgentSummary) => void;
  onClose: () => void;
}

/** Read-only "ID card" of a published agent: who made it, what it can do, its
 * instructions and files, its likes. Import is the only action; platform
 * admins may also remove it, with an optional message to the team. */
export default function MarketplaceAgentDialog({ agent, onImport, onClose }: MarketplaceAgentDialogProps) {
  const { t } = useTranslation();
  const { canAdmin } = useUserCapabilities();
  const { showSuccess, showError } = useToast();
  const [removing, setRemoving] = useState(false);
  const [reason, setReason] = useState("");
  const { data, isError, refetch } = useMarketplaceAgentQuery({ entryId: agent?.entry_id ?? "" }, { skip: !agent });
  const [unpublish, { isLoading: isUnpublishing }] = useUnpublishAgentMutation();
  // RTK Query may still hold the previously opened agent while the new one loads.
  const detail = data && data.entry_id === agent?.entry_id ? data : undefined;

  const closeAll = () => {
    setRemoving(false);
    setReason("");
    onClose();
  };

  const capabilityName = (capabilityId: string) => {
    const capability = detail?.capabilities?.find((c) => c.id === capabilityId);
    return capability ? t(capability.name, { defaultValue: capabilityId }) : capabilityId;
  };

  const confirmRemoval = async () => {
    if (!detail) return;
    try {
      await unpublish({
        teamId: detail.team_id,
        agentInstanceId: detail.agent_instance_id,
        unpublishAgentRequest: { expected_version: detail.version, reason: reason.trim() || null },
      }).unwrap();
      showSuccess({ summary: t("rework.agentMarketplace.removeSuccess", { name: detail.display_name }) });
      closeAll();
    } catch (error: unknown) {
      const view = marketplaceErrorView(error, t, capabilityName);
      // A retry must carry the current version, not the one this dialog opened with.
      if (view.stale) void refetch();
      showError({ summary: t("rework.agentMarketplace.removeError"), detail: view.message });
    }
  };

  return (
    <>
      <Dialog
        open={agent !== null}
        inactive={removing}
        title={agent?.display_name ?? ""}
        confirmLabel={t("rework.marketplace.agents.detail.import")}
        cancelLabel={t("rework.marketplace.agents.detail.close")}
        onConfirm={() => agent && onImport(agent)}
        onCancel={closeAll}
        maxWidth={960}
        scrollMode="children"
        dividers
        footerStart={
          canAdmin && detail ? (
            <Button
              type="button"
              color="error"
              variant="text"
              size="medium"
              icon={{ category: "outlined", type: "do_not_disturb_on" }}
              onClick={() => setRemoving(true)}
            >
              {t("rework.agentMarketplace.menu.remove")}
            </Button>
          ) : undefined
        }
      >
        {detail ? (
          <AgentIdCard detail={detail} />
        ) : isError ? (
          <p className={styles.status}>{t("rework.marketplace.agents.detail.loadError")}</p>
        ) : (
          <div className={styles.status}>
            <Spinner size={20} />
          </div>
        )}
      </Dialog>

      <Dialog
        open={removing}
        title={t("rework.marketplace.agents.remove.title")}
        confirmLabel={t("rework.marketplace.agents.remove.confirm")}
        confirmColor="error"
        confirmDisabled={isUnpublishing}
        onConfirm={() => void confirmRemoval()}
        onCancel={() => setRemoving(false)}
      >
        <div className={styles.removeBody}>
          <p>
            {t("rework.marketplace.agents.remove.message", {
              name: detail?.display_name ?? "",
              team: detail?.team_name ?? "",
            })}
          </p>
          <TextArea
            label={t("rework.marketplace.agents.remove.reasonLabel")}
            explanation={t("rework.marketplace.agents.remove.reasonHint")}
            value={reason}
            maxLength={REASON_MAX_LENGTH}
            rows={3}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      </Dialog>
    </>
  );
}

function AgentIdCard({ detail }: { detail: MarketplaceAgentDetail }) {
  const { t, i18n } = useTranslation();
  const { agentIconName } = useFrontendProperties();
  const likes = detail.like_count ?? 0;
  const imports = detail.import_count ?? 0;
  const updatedOn = formatMarketplaceDate(detail.published_at, i18n.language);
  const republished = detail.published_at !== detail.first_published_at;
  const instructions = detail.tuning_field_values?.[INSTRUCTIONS_FIELD];
  const capabilities = detail.capabilities ?? [];
  const files = detail.files ?? [];

  return (
    <div className={styles.card}>
      <div className={styles.infoColumn}>
        <div className={styles.summary}>
          <span className={styles.meta}>
            {detail.team_name
              ? t("rework.marketplace.agents.detail.publishedBy", { team: detail.team_name, date: updatedOn })
              : t("rework.marketplace.agents.card.updatedOn", { date: updatedOn })}
          </span>
          <header className={styles.identity}>
            <span className={styles.icon}>
              <Icon category="outlined" type={resolveAgentIcon(detail, agentIconName)} />
            </span>
            <div className={styles.identityText}>
              <span className={styles.name}>{detail.display_name}</span>
              {detail.role && <span className={styles.role}>{detail.role}</span>}
            </div>
          </header>

          <p className={styles.description}>{detail.description || t("rework.agentCard.noDescription")}</p>

          <ul className={styles.counters}>
            <li>
              {republished ? (
                <Tooltip
                  text={t("rework.marketplace.agents.detail.likesSinceUpdateTooltip", {
                    count: detail.likes_since_update ?? 0,
                    date: updatedOn,
                  })}
                >
                  <span className={styles.counterContent} tabIndex={0}>
                    <Icon category="outlined" type="favorite" />
                    {t("rework.agentMarketplace.likes", { count: likes })}
                  </span>
                </Tooltip>
              ) : (
                <>
                  <Icon category="outlined" type="favorite" />
                  {t("rework.agentMarketplace.likes", { count: likes })}
                </>
              )}
            </li>
            <li>
              <Icon category="outlined" type="download" />
              {t("rework.agentMarketplace.imports", { count: imports })}
            </li>
          </ul>
        </div>

        <section className={`${styles.section} ${styles.capabilitiesSection}`}>
          <h3 className={styles.sectionTitle}>{t("rework.marketplace.agents.detail.capabilitiesTitle")}</h3>
          {capabilities.length > 0 ? (
            <ul className={styles.capabilities}>
              {capabilities.map((capability) => (
                <li key={capability.id}>
                  <span className={styles.capabilityName}>{t(capability.name, { defaultValue: capability.id })}</span>
                  {capability.description && (
                    <span className={styles.capabilityDescription}>
                      {t(capability.description, { defaultValue: "" })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.muted}>{t("rework.marketplace.agents.detail.noCapabilities")}</p>
          )}
        </section>

        {files.length > 0 && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>{t("rework.marketplace.agents.detail.filesTitle")}</h3>
            <ul className={styles.files}>
              {files.map((file) => (
                <li key={`${file.capability_id}/${file.filename}`}>
                  <Icon category="outlined" type="description" />
                  <span className={styles.fileName}>{file.filename}</span>
                  <span className={styles.muted}>{formatBytes(file.size, i18n.language)}</span>
                </li>
              ))}
            </ul>
            <p className={styles.muted}>{t("rework.marketplace.agents.detail.filesHint")}</p>
          </section>
        )}
      </div>

      <section className={styles.instructionsColumn}>
        <h3 className={styles.sectionTitle}>{t("rework.marketplace.agents.detail.instructionsTitle")}</h3>
        {typeof instructions === "string" && instructions.trim() ? (
          <PromptHighlight value={instructions} className={styles.instructions} />
        ) : (
          <p className={styles.muted}>{t("rework.marketplace.agents.detail.noInstructions")}</p>
        )}
      </section>
    </div>
  );
}
