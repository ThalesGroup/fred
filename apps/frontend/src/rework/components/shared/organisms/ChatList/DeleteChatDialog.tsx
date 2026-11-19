// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { abortTurn } from "@core/hooks/backgroundTurns";
import { clearToolApprovalGrants } from "@core/utils/toolApprovalGrants";
import Button from "@shared/atoms/Button/Button";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import { useGetTraceConsentQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ChatList.module.scss";

type DeleteChoice = "everyone" | "keep";

export function DeleteChatDialog({
  teamId,
  sessionId,
  agentInstanceId,
  label,
  onClose,
  onDeleted,
}: {
  teamId: string;
  sessionId: string;
  agentInstanceId: string;
  label: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: "rework.sidebar.chatList.deleteDialog" });
  const optionsName = useId();
  const [choice, setChoice] = useState<DeleteChoice>();
  const [error, setError] = useState(false);
  const consent = useGetTraceConsentQuery({ teamId, sessionId }, { refetchOnMountOrArgChange: true });
  const [remove, removing] = useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation();
  const grant = consent.currentData?.consent;
  const ready = consent.isSuccess && !consent.isFetching && !consent.isError;

  async function confirm() {
    if (!ready || removing.isLoading || (grant && !choice)) return;
    setError(false);
    abortTurn(sessionId);
    try {
      await remove({ teamId, sessionId, keepSharedDiagnostics: Boolean(grant && choice === "keep") }).unwrap();
    } catch (failure) {
      setError(true);
      if (typeof failure === "object" && failure !== null && "status" in failure && failure.status === 409) {
        setChoice(undefined);
        void consent.refetch();
      }
      return;
    }
    clearToolApprovalGrants({ userId: KeyCloakService.GetUserId(), agentInstanceId, sessionId });
    onDeleted();
  }

  return (
    <ConfirmationDialog
      open
      title={t("title")}
      message={ready ? t(grant ? "sharedMessage" : "message", { name: label }) : undefined}
      details={
        <>
          {consent.isError ? (
            <>
              <p role="alert">{t("consentError")}</p>
              <Button size="small" variant="text" color="secondary" onClick={() => void consent.refetch()}>
                {t("retry")}
              </Button>
            </>
          ) : !ready ? (
            <p role="status">{t("checkingConsent")}</p>
          ) : grant ? (
            <fieldset className={styles.deleteOptions} disabled={removing.isLoading}>
              <legend>{t("sharedOptions")}</legend>
              {(["everyone", "keep"] as const).map((value) => (
                <label key={value}>
                  <input type="radio" name={optionsName} checked={choice === value} onChange={() => setChoice(value)} />
                  <span>
                    <strong>{t(value)}</strong>
                    <span>{t(value === "keep" ? "keepHelp" : "everyoneHelp", { turn: grant.cutoff.turn_number })}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          ) : null}
          {error && <p role="alert">{t("error")}</p>}
        </>
      }
      confirmLabel={t(grant && choice ? choice : "confirm")}
      cancelLabel={t("cancel")}
      criticalAction
      confirmDisabled={!ready || removing.isLoading || Boolean(grant && !choice)}
      dismissible={!removing.isLoading}
      onConfirm={() => void confirm()}
      onCancel={() => {
        if (!removing.isLoading) onClose();
      }}
    />
  );
}
