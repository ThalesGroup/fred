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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import CopyToTeamsDialog, { type CopyTargetStatus } from "@shared/organisms/CopyToTeamsDialog/CopyToTeamsDialog.tsx";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import {
  type ManagedAgentInstanceSummary,
  useGetAgentInstanceCopyTargetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyTargetsGetQuery,
  usePostAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPostMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./CopyAgentDialog.module.scss";

interface CopyAgentDialogProps {
  /** The agent to copy; the dialog is open while it is set. */
  instance: ManagedAgentInstanceSummary | null;
  onClose: () => void;
}

/** "Copy to…": copies an agent into the caller's other spaces, showing before
 * the copy which teams lack the agent template or some of its capabilities. */
export default function CopyAgentDialog({ instance, onClose }: CopyAgentDialogProps) {
  const { t } = useTranslation();
  const { showSuccess, showWarn, showError } = useToast();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const sourceTeamId = instance?.team_id ?? "";
  const agentInstanceId = instance?.agent_instance_id ?? "";

  const { data: targets, isError } =
    useGetAgentInstanceCopyTargetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyTargetsGetQuery(
      { teamId: sourceTeamId, agentInstanceId },
      // Enablement changes elsewhere; always read the current state.
      { skip: !instance, refetchOnMountOrArgChange: true },
    );
  const [copyAgent, { isLoading }] =
    usePostAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPostMutation();

  const statusByTeamId = useMemo(() => {
    const statuses: Record<string, CopyTargetStatus> = {};
    for (const target of targets?.targets ?? []) {
      if (!target.template_enabled) {
        statuses[target.team_id] = { disabledReason: t("rework.agentCard.copyDialog.templateDisabled") };
      } else if (target.missing_capabilities && target.missing_capabilities.length > 0) {
        const missing = target.missing_capabilities;
        statuses[target.team_id] = {
          warning: {
            label: t("rework.agentCard.copyDialog.missingCapabilities", { count: missing.length }),
            detail: (
              <div className={styles.missingList}>
                <span className={styles.missingTitle}>{t("rework.agentCard.copyDialog.missingCapabilitiesTitle")}</span>
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

  const someTeamLacksCapabilities = Object.values(statusByTeamId).some((status) => status.warning);

  const infoRows: Array<[string, string]> = [
    ["copiedLabel", "copied"],
    ["resetLabel", "reset"],
    ["recreatedLabel", "recreated"],
    ["notCopiedLabel", "notCopied"],
  ];
  const info = (
    <div className={styles.infoTooltip}>
      {infoRows.map(([label, value]) => (
        <div key={label} className={styles.infoRow}>
          <span className={styles.infoLabel}>{t(`rework.agentCard.copyDialog.info.${label}`)}</span>
          <span className={styles.infoValue}>{t(`rework.agentCard.copyDialog.info.${value}`)}</span>
        </div>
      ))}
    </div>
  );

  const teamName = (teamId: string) =>
    teamId === activeTeam?.id
      ? t("rework.copyToTeams.personalSpace")
      : (availableTeams.find((team) => team.id === teamId)?.name ?? teamId);

  const handleConfirm = async (teamIds: string[]) => {
    if (!instance || teamIds.length === 0) return;
    try {
      const { results } = await copyAgent({
        teamId: sourceTeamId,
        agentInstanceId,
        agentCopyRequest: { target_team_ids: teamIds },
      }).unwrap();
      const copied = results.filter((r) => r.agent);
      const failed = results.filter((r) => r.error);
      const partial = copied.filter((r) => r.dropped_capabilities && r.dropped_capabilities.length > 0);
      if (copied.length > 0) {
        showSuccess({ summary: t("rework.agentCard.copyDialog.successToast", { count: copied.length }) });
      }
      if (partial.length > 0) {
        showWarn({
          summary: t("rework.agentCard.copyDialog.droppedToast"),
          detail: partial
            .map((r) =>
              t("rework.agentCard.copyDialog.droppedDetail", {
                team: teamName(r.team_id),
                capabilities: (r.dropped_capabilities ?? []).map((c) => t(c.name, { defaultValue: c.id })).join(", "),
              }),
            )
            .join(" · "),
        });
      }
      const notices = copied.flatMap((r) =>
        (r.notices ?? []).map(
          (n) => `${teamName(r.team_id)} — ${t(n.capability.name, { defaultValue: n.capability.id })} : ${n.message}`,
        ),
      );
      if (notices.length > 0) {
        showWarn({ summary: t("rework.agentCard.copyDialog.noticesToast"), detail: notices.join(" · ") });
      }
      if (failed.length > 0) {
        showError({
          summary: t("rework.agentCard.copyDialog.errorToast", { count: failed.length }),
          detail: failed.map((r) => `${teamName(r.team_id)} — ${r.error}`).join(" · "),
        });
      }
      onClose();
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: t("rework.agentCard.copyDialog.errorToast", { count: teamIds.length }),
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  return (
    <CopyToTeamsDialog
      open={instance !== null}
      title={t("rework.agentCard.copyDialog.title", { name: instance?.display_name ?? "" })}
      titleInfo={info}
      subtitle={t("rework.agentCard.copyDialog.subtitle")}
      explanation={
        isError
          ? t("rework.agentCard.copyDialog.loadError")
          : someTeamLacksCapabilities
            ? t("rework.agentCard.copyDialog.explanation")
            : undefined
      }
      confirmLabel={t("rework.agentCard.copyDialog.confirm")}
      noEditableTeamsLabel={t("rework.agentCard.copyDialog.noEditableTeams")}
      originTeamId={sourceTeamId}
      statusByTeamId={statusByTeamId}
      isSubmitting={isLoading}
      onConfirm={(teamIds) => void handleConfirm(teamIds)}
      onClose={onClose}
    />
  );
}
