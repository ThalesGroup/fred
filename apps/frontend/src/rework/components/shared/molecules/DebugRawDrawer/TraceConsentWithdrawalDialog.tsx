// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useRevokeTraceConsentMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";

export function TraceConsentWithdrawalDialog({
  spaceId,
  sessionId,
  onClose,
}: {
  spaceId: string;
  sessionId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: "chatbot.traceConsent" });
  const [revoke, revoking] = useRevokeTraceConsentMutation();
  const [error, setError] = useState(false);

  async function confirm() {
    if (revoking.isLoading) return;
    setError(false);
    try {
      await revoke({ spaceId, sessionId }).unwrap();
      onClose();
    } catch {
      setError(true);
    }
  }

  return (
    <ConfirmationDialog
      open
      title={t("revokeTitle")}
      message={t("revokeDescription")}
      details={error && <p role="alert">{t("revokeError")}</p>}
      confirmLabel={t("revoke")}
      cancelLabel={t("cancel")}
      confirmDisabled={revoking.isLoading}
      dismissible={!revoking.isLoading}
      onConfirm={() => void confirm()}
      onCancel={() => {
        if (!revoking.isLoading) onClose();
      }}
    />
  );
}
