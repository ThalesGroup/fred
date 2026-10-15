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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import CopyToTeamsDialog, { type CopyTargetStatus } from "@shared/organisms/CopyToTeamsDialog/CopyToTeamsDialog.tsx";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap";
import {
  useImportMarketplaceAgentMutation,
  useMarketplaceAgentImportTargetsQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  AgentCopyCapability,
  AgentCopyResult,
  MarketplaceAgentSummary,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { marketplaceErrorView } from "../../../TeamAgentsPage/agentMarketplace.ts";
import styles from "./ImportAgentDialog.module.css";

const LOCALIZED_RESULT_ERRORS = ["marketplace_publishing_team", "agent_name_conflict"];

interface ImportAgentDialogProps {
  /** The agent to import; the dialog is open while it is set. */
  agent: MarketplaceAgentSummary | null;
  onClose: () => void;
}

/** Imports a published agent into the caller's spaces: per-team readiness and
 * losses first, then one result per team with what to set up again there. */
export default function ImportAgentDialog({ agent, onClose }: ImportAgentDialogProps) {
  const { t, i18n } = useTranslation();
  const { showError } = useToast();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const [results, setResults] = useState<AgentCopyResult[] | null>(null);
  const entryId = agent?.entry_id ?? "";

  const {
    data: targets,
    isError,
    isFetching,
  } = useMarketplaceAgentImportTargetsQuery(
    { entryId },
    // Enablement changes elsewhere; always read the current state.
    { skip: !agent, refetchOnMountOrArgChange: true },
  );
  const [importAgent, { isLoading }] = useImportMarketplaceAgentMutation();

  useEffect(() => {
    if (!agent) setResults(null);
  }, [agent]);

  const capabilityLabel = (capability: AgentCopyCapability) => t(capability.name, { defaultValue: capability.id });

  const statusByTeamId = useMemo(() => {
    const statuses: Record<string, CopyTargetStatus> = {};
    for (const target of targets?.targets ?? []) {
      if (!target.template_enabled) {
        statuses[target.team_id] = { disabledReason: t("rework.marketplace.agents.import.typeNotEnabled") };
      } else if (target.missing_capabilities && target.missing_capabilities.length > 0) {
        const missing = target.missing_capabilities;
        statuses[target.team_id] = {
          warning: {
            label: t("rework.marketplace.agents.import.loses", { count: missing.length }),
            detail: (
              <div className={styles.missingList}>
                <span className={styles.missingTitle}>{t("rework.marketplace.agents.import.losesTitle")}</span>
                {missing.map((capability) => (
                  <span key={capability.id}>{t(capability.name, { defaultValue: capability.id })}</span>
                ))}
              </div>
            ),
          },
        };
      }
    }
    return statuses;
  }, [targets, t]);

  const teamName = (teamId: string) =>
    teamId === activeTeam?.id
      ? t("rework.copyToTeams.personalSpace")
      : (availableTeams.find((team) => team.id === teamId)?.name ?? teamId);

  const resultError = (result: AgentCopyResult) =>
    result.error_code && LOCALIZED_RESULT_ERRORS.includes(result.error_code)
      ? t(`rework.marketplace.agents.import.errors.${result.error_code}`)
      : t("rework.marketplace.agents.import.errors.generic");

  const handleConfirm = async (teamIds: string[]) => {
    if (!agent || teamIds.length === 0) return;
    try {
      const response = await importAgent({
        entryId: agent.entry_id,
        marketplaceAgentImportRequest: {
          target_team_ids: teamIds,
          locale: i18n.language?.startsWith("fr") ? "fr" : "en",
        },
      }).unwrap();
      setResults(response.results);
    } catch (error: unknown) {
      showError({
        summary: t("rework.marketplace.agents.import.errorToast"),
        detail: marketplaceErrorView(error, t, (id) => id).message,
      });
    }
  };

  const publishingTeam = agent?.team_name ?? "";
  const info = (
    <div className={styles.infoTooltip}>
      {(["copied", "reset", "recreated", "notCopied"] as const).map((row) => (
        <div key={row} className={styles.infoRow}>
          <span className={styles.infoLabel}>{t(`rework.marketplace.agents.import.info.${row}Label`)}</span>
          <span className={styles.infoValue}>{t(`rework.marketplace.agents.import.info.${row}`)}</span>
        </div>
      ))}
    </div>
  );

  if (agent && results) {
    return (
      <Dialog
        open
        title={t("rework.marketplace.agents.import.resultTitle", { name: agent.display_name })}
        confirmLabel={t("rework.marketplace.agents.detail.close")}
        hideCancel
        onConfirm={onClose}
        onCancel={onClose}
      >
        <ul className={styles.results}>
          {results.map((result) =>
            result.agent ? (
              <li key={result.team_id} className={styles.result} data-outcome="success">
                <span className={styles.resultTitle}>
                  <span className={styles.resultIcon}>
                    <Icon category="outlined" type="check_circle" />
                  </span>
                  {t("rework.marketplace.agents.import.importedInto", { team: teamName(result.team_id) })}
                </span>
                {result.agent.display_name !== agent.display_name && (
                  <span className={styles.resultLine}>
                    {t("rework.marketplace.agents.import.renamed", { name: result.agent.display_name })}
                  </span>
                )}
                <span className={styles.resultLine}>{t("rework.marketplace.agents.import.toReconfigure")}</span>
                {(result.dropped_capabilities ?? []).length > 0 && (
                  <span className={styles.resultLine}>
                    {t("rework.marketplace.agents.import.dropped", {
                      capabilities: (result.dropped_capabilities ?? []).map(capabilityLabel).join(", "),
                    })}
                  </span>
                )}
                {(result.notices ?? []).map((notice) => (
                  <span key={notice.capability.id} className={styles.resultLine}>
                    {t("rework.marketplace.agents.import.notice", {
                      capability: capabilityLabel(notice.capability),
                      message: notice.message,
                    })}
                  </span>
                ))}
              </li>
            ) : (
              <li key={result.team_id} className={styles.result} data-outcome="error">
                <span className={styles.resultTitle}>
                  <span className={styles.resultIcon}>
                    <Icon category="outlined" type="error" />
                  </span>
                  {t("rework.marketplace.agents.import.failedInto", { team: teamName(result.team_id) })}
                </span>
                <span className={styles.resultLine}>{resultError(result)}</span>
              </li>
            ),
          )}
        </ul>
      </Dialog>
    );
  }

  return (
    <CopyToTeamsDialog
      open={agent !== null}
      title={t("rework.marketplace.agents.import.title", { name: agent?.display_name ?? "" })}
      titleInfo={info}
      subtitle={t("rework.marketplace.agents.import.subtitle")}
      explanation={
        isError
          ? t("rework.agentCard.copyDialog.loadError")
          : t("rework.marketplace.agents.import.independent", { team: publishingTeam })
      }
      confirmLabel={t("rework.marketplace.agents.import.confirm")}
      noEditableTeamsLabel={t("rework.marketplace.agents.import.noEditableTeams")}
      excludedTeamIds={agent ? [agent.team_id] : undefined}
      statusByTeamId={statusByTeamId}
      confirmBlocked={!targets || isFetching || isError}
      isSubmitting={isLoading}
      onConfirm={(teamIds) => void handleConfirm(teamIds)}
      onClose={onClose}
    />
  );
}
